import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import aiohttp
from base64 import b64encode
import unicodedata
import re
import os

from src.config import JELLYFIN_URL, API_KEY, TMDB_KEY
from src.constants import POSTER_DIR, COLLECTIONS_DIR, OUTPUT_FILENAME, MISSING, EXTRA_FOLDER, \
    COVER_DIR

logger = logging.getLogger(__name__)

class UpdateCover:
    def __init__(self):
        self.directory_lookup: Dict[str, Path] = {}
        self.used_folders: List[Path] = []
        self.missing_folders: List[str] = []
        self.extra_folders: List[Path] = []
        self.scan_directories()

    def scan_directories(self):
        """Scan all directories once and create a lookup dictionary."""
        self.directory_lookup.clear()
        for base_dir in [POSTER_DIR, COLLECTIONS_DIR]:
            for item_dir in base_dir.glob('*'):
                if item_dir.is_dir():
                    key = item_dir.name.lower()
                    self.directory_lookup[key] = item_dir

    def get_item_directory(self, item: Dict) -> Optional[Path]:
        item_type = item.get('Type', 'Series' if 'Seasons' in item else 'Movie')
        item_name = self.clean_name(item.get('Name', '').strip())
        item_original_title = self.clean_name(item.get('OriginalTitle', item_name).strip())
        item_year = item.get('Year')

        possible_keys = []
        if item_type == "BoxSet":
            possible_keys = [
                item_name.lower(),
            ]
        else:
            possible_keys = [
                f"{item_original_title} ({item_year})".lower(),
                f"{item_name} ({item_year})".lower()
            ]

        for key in possible_keys:
            if key in self.directory_lookup:
                self.used_folders.append(self.directory_lookup[key])
                return self.directory_lookup[key]

        # If we reach here, no directory was found
        base_dir = COLLECTIONS_DIR if item_type == "BoxSet" else POSTER_DIR

        if base_dir == COLLECTIONS_DIR:
            missing_name = f"{item_original_title}" if item_original_title and not any(
                ord(char) > 127 for char in item_original_title) else f"{item_name}"
        else:
            missing_name = f"{item_original_title} ({item_year})" if item_original_title and not any(
                ord(char) > 127 for char in item_original_title) else f"{item_name} ({item_year})"

        missing_folder = f"Folder not found: {base_dir / missing_name}"
        self.missing_folders.append(missing_folder)
        logger.warning(missing_folder)
        return None

    @staticmethod
    def clean_name(name: str) -> str:
        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '&', "'", '!', '?', '[', ']', '!', '&']
        for char in invalid_chars:
            name = name.replace(char, '')
        return name

    @staticmethod
    def find_image(item_dir: Path, filename: str) -> Optional[Path]:
        for ext in ['png', 'jpg', 'jpeg', 'webp']:
            image_path = item_dir / f"{filename}.{ext}"
            if image_path.exists():
                return image_path
        return None

    async def update_jellyfin(self, id: str, image_path: Path, item: Dict, image_type: str = 'Primary', extra_info: str = ''):
        endpoint = f'/Items/{id}/Images/{image_type}/0'
        url = f"{JELLYFIN_URL}{endpoint}"
        headers = {
            'X-Emby-Token': API_KEY,
            'Content-Type': self.get_content_type(str(image_path))
        }

        if not image_path.exists():
            logger.warning(f"Image file not found: {image_path}. Skipping.")
            return

        with image_path.open('rb') as file:
            image_data = file.read()
            image_base64 = b64encode(image_data)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, data=image_base64) as response:
                    response.raise_for_status()
                    display_name = item['Name']
                    log_message = f'Updated {image_type} image for {self.clean_name(display_name)}'
                    if extra_info:
                        log_message += f' - {extra_info}'
                    log_message += ' successfully.'
                    logger.info(log_message)
            except aiohttp.ClientResponseError as e:
                display_name = item['Name']
                logger.error(f'Error updating {image_type} image for {self.clean_name(display_name)}{" - " + extra_info if extra_info else ""}. Status Code: {e.status}')
                logger.error(f'Response: {e.message}')


    @staticmethod
    def get_content_type(file_path: str) -> str:
        ext = file_path.split('.')[-1].lower()
        return {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'webp': 'image/webp'
        }.get(ext, 'application/octet-stream')

    async def process_item(self, item: Dict):
        item_dir = self.get_item_directory(item)
        if not item_dir:
            return

        # Update main poster
        main_poster = self.find_image(item_dir, 'poster')
        if main_poster:
            await self.update_jellyfin(item['Id'], main_poster, item, 'Primary')

        # Update backdrop
        backdrop = self.find_image(item_dir, 'backdrop')
        if backdrop:
            await self.update_jellyfin(item['Id'], backdrop, item, 'Backdrop')

        # Process seasons and episodes for series
        if 'Seasons' in item:
            for season_name, season_data in item['Seasons'].items():
                season_number = season_name.split()[-1]
                season_image = self.find_image(item_dir, f'Season{season_number.zfill(2)}')
                if season_image:
                    await self.update_jellyfin(season_data['Id'], season_image, item, 'Primary', f'Season {season_number}')

                for episode_number, episode_id in season_data.get('Episodes', {}).items():
                    episode_image = self.find_image(item_dir, f'S{season_number.zfill(2)}E{episode_number.zfill(2)}')
                    if episode_image:
                        await self.update_jellyfin(episode_id, episode_image, item, 'Primary', f'S{season_number}E{episode_number}')

    async def run(self):
        self.missing_folders.clear()
        self.extra_folders.clear()
        with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
            items = json.load(f)

        tasks = [self.process_item(item) for item in items]
        await asyncio.gather(*tasks)

        self.save_missing_folders()

    def save_missing_folders(self):
        all_folders = set(POSTER_DIR.glob('*')) | set(COLLECTIONS_DIR.glob('*'))
        self.extra_folders = list(all_folders - set(self.used_folders))

        with open(MISSING, 'w', encoding='utf-8') as f:
            for folder in self.missing_folders:
                f.write(f"{folder}\n")

        if os.path.getsize(MISSING) == 0:
            os.remove(MISSING)

        with open(EXTRA_FOLDER, 'w', encoding='utf-8') as f:
            for folder in self.extra_folders:
                f.write(f"Didn't use Folder: {folder}\n")

        if os.path.getsize(EXTRA_FOLDER) == 0:
            os.remove(EXTRA_FOLDER)

        missing_exists = os.path.exists(MISSING)
        extra_exists = os.path.exists(EXTRA_FOLDER)

        if missing_exists and extra_exists:
            logger.info(f"Saved missing and unused folders to {MISSING} and {EXTRA_FOLDER}")
        elif missing_exists:
            logger.info(f"Saved missing folders to {MISSING}, but no unused folders.")
        elif extra_exists:
            logger.info(f"Saved unused folders to {EXTRA_FOLDER}, but no missing folders.")
        else:
            logger.info("No missing or unused folders to save.")


if __name__ == "__main__":
    updater = UpdateCover()
    asyncio.run(updater.run())