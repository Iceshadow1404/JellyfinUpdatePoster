import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import aiohttp
from base64 import b64encode
import gc
import os

from src.config import JELLYFIN_URL, API_KEY, TMDB_KEY, chunk_size
from src.constants import POSTER_DIR, COLLECTIONS_DIR, OUTPUT_FILENAME, MISSING, EXTRA_FOLDER, \
    COVER_DIR

logger = logging.getLogger(__name__)


class UpdateCover:
    def __init__(self):
        self.directory_lookup: Dict[str, Path] = {}
        self.used_folders: List[Path] = []
        self.missing_folders: List[str] = []
        self.extra_folders: List[Path] = []
        self.items_to_process: List[Dict] = []

    async def initialize(self):
        """Initialize by scanning directories and loading items."""
        logger.info("Starting initialization...")
        self.scan_directories()
        await self.load_items()
        logger.info(
            f"Initialization complete. Found {len(self.directory_lookup)} directories and {len(self.items_to_process)} items to process.")

    def scan_directories(self):
        """Scan all directories once and create a lookup dictionary."""
        logger.info("Scanning directories...")
        self.directory_lookup.clear()
        for base_dir in [POSTER_DIR, COLLECTIONS_DIR]:
            logger.info(f"Scanning {base_dir}")
            for item_dir in base_dir.glob('*'):
                if item_dir.is_dir():
                    key = item_dir.name.lower()
                    self.directory_lookup[key] = item_dir
        logger.info(f"Directory scan complete. Found {len(self.directory_lookup)} directories.")

    async def load_items(self):
        """Load all items from the output file."""
        logger.info(f"Loading items from {OUTPUT_FILENAME}")
        try:
            with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
                self.items_to_process = json.load(f)
            logger.info(f"Successfully loaded {len(self.items_to_process)} items.")
        except Exception as e:
            logger.error(f"Error loading items: {str(e)}")
            self.items_to_process = []

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

    async def update_jellyfin(self, id: str, image_path: Path, item: Dict, image_type: str = 'Primary',
                              extra_info: str = ''):
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

            image_data = None
            try:
                with image_path.open('rb') as file:
                    image_data = file.read()
                    image_base64 = b64encode(image_data)
            finally:
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
            logger.error(
                f'Error updating {image_type} image for {self.clean_name(display_name)}{" - " + extra_info if extra_info else ""}. Error: {str(e)}')
        finally:
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

            main_poster = self.find_image(item_dir, 'poster')
            if main_poster:
                await self.update_jellyfin(item['Id'], main_poster, item, 'Primary')
                gc.collect()

            backdrop = self.find_image(item_dir, 'backdrop')
            if backdrop:
                await self.update_jellyfin(item['Id'], backdrop, item, 'Backdrop')
                gc.collect()

            if 'Seasons' in item:
                for season_name, season_data in item['Seasons'].items():
                    season_number = season_name.split()[-1]
                    season_image = self.find_image(item_dir, f'Season{season_number.zfill(2)}')
                    if season_image:
                        await self.update_jellyfin(season_data['Id'], season_image, item, 'Primary',
                                                   f'Season {season_number}')
                        gc.collect()

                    for episode_number, episode_id in season_data.get('Episodes', {}).items():
                        episode_image = self.find_image(item_dir,
                                                        f'S{season_number.zfill(2)}E{episode_number.zfill(2)}')
                        if episode_image:
                            await self.update_jellyfin(episode_id, episode_image, item, 'Primary',
                                                       f'S{season_number}E{episode_number}')
                            gc.collect()

        except Exception as e:
            logger.error(f"Error processing item {item.get('Name', 'Unknown')}: {str(e)}")
        finally:
            gc.collect()

    def save_missing_folders(self):
        try:
            all_folders = set()

            for chunk in self._chunk_iterator(POSTER_DIR.glob('*'), chunk_size):
                all_folders.update(chunk)
                gc.collect()

            for chunk in self._chunk_iterator(COLLECTIONS_DIR.glob('*'), chunk_size):
                all_folders.update(chunk)
                gc.collect()

            self.extra_folders = list(all_folders - set(self.used_folders))
            gc.collect()

            if self.missing_folders:
                with open(MISSING, 'w', encoding='utf-8') as f:
                    for folder in self.missing_folders:
                        f.write(f"{folder}\n")

            if os.path.exists(MISSING) and os.path.getsize(MISSING) == 0:
                os.remove(MISSING)

            if self.extra_folders:
                with open(EXTRA_FOLDER, 'w', encoding='utf-8') as f:
                    for folder in self.extra_folders:
                        f.write(f"Didn't use Folder: {folder}\n")

            if os.path.exists(EXTRA_FOLDER) and os.path.getsize(EXTRA_FOLDER) == 0:
                os.remove(EXTRA_FOLDER)

            self._log_results()

        except Exception as e:
            logger.error(f"Error in save_missing_folders: {str(e)}")
        finally:
            gc.collect()

    def _log_results(self):
        """Log the results of the missing and extra folders check."""
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

    @staticmethod
    def _chunk_iterator(iterable, chunk_size):
        chunk = []
        for item in iterable:
            chunk.append(item)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
                gc.collect()
        if chunk:
            yield chunk

    async def process_items(self):
        """Process items using a queue for more even distribution."""
        logger.info(f"Starting to process {len(self.items_to_process)} items...")

        # Create a queue of items to process
        queue = asyncio.Queue()
        for item in self.items_to_process:
            await queue.put(item)

        # Create worker function
        async def worker():
            while True:
                try:
                    item = await queue.get()
                    await self.process_item(item)
                    queue.task_done()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error processing item: {str(e)}")
                finally:
                    gc.collect()

        try:
            # Start a fixed number of worker tasks
            workers = [asyncio.create_task(worker()) for _ in range(5)]  # 5 concurrent workers

            # Wait for all items to be processed
            await queue.join()

            # Cancel workers
            for w in workers:
                w.cancel()

            # Wait for worker cancellation
            await asyncio.gather(*workers, return_exceptions=True)

        except Exception as e:
            logger.error(f"Error in process_items: {str(e)}")
        finally:
            gc.collect()

    async def run(self):
        """Main execution method with separated initialization and processing."""
        try:
            await self.initialize()  # First scan directories and load items
            await self.process_items()  # Then process all items
            self.save_missing_folders()  # Finally save missing folders info

        except Exception as e:
            logger.error(f"Error in run method: {str(e)}")
        finally:
            gc.collect()
            logger.info("Process completed. Memory cleanup finished.")


if __name__ == "__main__":
    updater = UpdateCover()
    asyncio.run(updater.run())