import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import aiohttp
from base64 import b64encode
import gc
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
        try:
            endpoint = f'/Items/{id}/Images/{image_type}/0'
            url = f"{JELLYFIN_URL}{endpoint}"
            headers = {
                'X-Emby-Token': API_KEY,
                'Content-Type': self.get_content_type(str(image_path))
            }

            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}. Skipping.")
                return

            # Use context manager for file handling to ensure proper cleanup
            image_data = None
            try:
                with image_path.open('rb') as file:
                    image_data = file.read()
                    image_base64 = b64encode(image_data)
            finally:
                # Explicitly delete the raw image data after encoding
                del image_data
                gc.collect()

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=image_base64) as response:
                    response.raise_for_status()
                    display_name = item['Name']
                    log_message = f'Updated {image_type} image for {self.clean_name(display_name)}'
                    if extra_info:
                        log_message += f' - {extra_info}'
                    log_message += ' successfully.'
                    logger.info(log_message)

        except Exception as e:
            display_name = item['Name']
            logger.error(f'Error updating {image_type} image for {self.clean_name(display_name)}{" - " + extra_info if extra_info else ""}. Error: {str(e)}')
        finally:
            # Clear the encoded image data
            if 'image_base64' in locals():
                del image_base64
            gc.collect()


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
        try:
            item_dir = self.get_item_directory(item)
            if not item_dir:
                return

            # Update main poster
            main_poster = self.find_image(item_dir, 'poster')
            if main_poster:
                await self.update_jellyfin(item['Id'], main_poster, item, 'Primary')
                gc.collect()

            # Update backdrop
            backdrop = self.find_image(item_dir, 'backdrop')
            if backdrop:
                await self.update_jellyfin(item['Id'], backdrop, item, 'Backdrop')
                gc.collect()

            # Process seasons and episodes for series
            if 'Seasons' in item:
                for season_name, season_data in item['Seasons'].items():
                    season_number = season_name.split()[-1]
                    season_image = self.find_image(item_dir, f'Season{season_number.zfill(2)}')
                    if season_image:
                        await self.update_jellyfin(season_data['Id'], season_image, item, 'Primary', f'Season {season_number}')
                        gc.collect()

                    for episode_number, episode_id in season_data.get('Episodes', {}).items():
                        episode_image = self.find_image(item_dir, f'S{season_number.zfill(2)}E{episode_number.zfill(2)}')
                        if episode_image:
                            await self.update_jellyfin(episode_id, episode_image, item, 'Primary', f'S{season_number}E{episode_number}')
                            gc.collect()

        except Exception as e:
            logger.error(f"Error processing item {item.get('Name', 'Unknown')}: {str(e)}")
        finally:
            # Ensure cleanup after processing each item
            gc.collect()

    def save_missing_folders(self):
        """Save information about missing and extra folders with memory optimization."""
        try:
            # Process folders in chunks to optimize memory usage
            all_folders = set()
            chunk_size = 100  # Adjust based on your needs

            # Collect POSTER_DIR folders
            for chunk in self._chunk_iterator(POSTER_DIR.glob('*'), chunk_size):
                all_folders.update(chunk)
                gc.collect()

            # Collect COLLECTIONS_DIR folders
            for chunk in self._chunk_iterator(COLLECTIONS_DIR.glob('*'), chunk_size):
                all_folders.update(chunk)
                gc.collect()

            # Calculate extra folders
            self.extra_folders = list(all_folders - set(self.used_folders))
            gc.collect()

            # Write missing folders
            if self.missing_folders:
                with open(MISSING, 'w', encoding='utf-8') as f:
                    for folder in self.missing_folders:
                        f.write(f"{folder}\n")

            # Remove empty missing file
            if os.path.exists(MISSING) and os.path.getsize(MISSING) == 0:
                os.remove(MISSING)

            # Write extra folders
            if self.extra_folders:
                with open(EXTRA_FOLDER, 'w', encoding='utf-8') as f:
                    for folder in self.extra_folders:
                        f.write(f"Didn't use Folder: {folder}\n")

            # Remove empty extra folder file
            if os.path.exists(EXTRA_FOLDER) and os.path.getsize(EXTRA_FOLDER) == 0:
                os.remove(EXTRA_FOLDER)

            # Log results
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

        except Exception as e:
            logger.error(f"Error in save_missing_folders: {str(e)}")
        finally:
            gc.collect()

    @staticmethod
    def _chunk_iterator(iterable, chunk_size):
        """Helper method to process iterables in chunks."""
        chunk = []
        for item in iterable:
            chunk.append(item)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
                gc.collect()
        if chunk:
            yield chunk

    async def run(self):
        try:
            self.missing_folders.clear()
            self.extra_folders.clear()

            # Load items in chunks to reduce memory usage
            chunk_size = 50
            with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
                items = json.load(f)

            for i in range(0, len(items), chunk_size):
                chunk = items[i:i + chunk_size]
                tasks = [self.process_item(item) for item in chunk]
                await asyncio.gather(*tasks)
                gc.collect()  # Force garbage collection after each chunk

                # Log progress
                logger.info(f"Processed items {i + 1} to {min(i + chunk_size, len(items))} of {len(items)}")

            self.save_missing_folders()

        except Exception as e:
            logger.error(f"Error in run method: {str(e)}")
        finally:
            # Final cleanup
            gc.collect()
            logger.info("Memory cleanup completed")


if __name__ == "__main__":
    updater = UpdateCover()
    asyncio.run(updater.run())