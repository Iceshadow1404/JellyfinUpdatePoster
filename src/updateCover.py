import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import aiohttp
from base64 import b64encode
import gc
import os
import time
import concurrent.futures
from functools import cached_property
import psutil

from src.config import JELLYFIN_URL, API_KEY, TMDB_KEY
from src.constants import POSTER_DIR, COLLECTIONS_DIR, OUTPUT_FILENAME, MISSING, EXTRA_FOLDER, LANGUAGE_DATA_FILENAME

logger = logging.getLogger(__name__)

class UpdateCover:
    @cached_property
    def directory_cache(self):
        """Lazy-loaded directory cache"""
        return {}

    def __init__(self):
        self.directory_lookup: Dict[str, Path] = {}
        self.used_folders: List[Path] = []
        self.missing_folders: List[str] = []
        self.extra_folders: List[Path] = []
        self.items_to_process: List[Dict] = []
        self.session: Optional[aiohttp.ClientSession] = None
        self.processing_start_time = None
        self.processing_end_time = None
        self.semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
        self.batch_size = 20  # Number of items to process in parallel

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.directory_cache.clear()
            gc.collect()
            await self.session.close()

    async def initialize(self):
        """Initialize by scanning directories and loading items."""
        self.missing_folders = []
        self.scan_directories()
        self.processing_start_time = time.time()
        
        await self.load_items()
        logger.info(
            f"Initialization complete. Found {len(self.directory_lookup)} directories and {len(self.items_to_process)} items to process.")

    async def read_image(self, image_path: Path) -> bytes:
        """Read image data with caching"""
        try:
            with image_path.open('rb', buffering=1024*1024) as file:  # Buffered reading
                data = file.read()
                return data
        except Exception as e:
            logger.error(f"Error reading image {image_path}: {str(e)}")
            raise

    def scan_directories(self):
        """Optimized directory scanning using ThreadPoolExecutor for I/O operations"""
        logger.info("Scanning directories...")
        self.directory_lookup.clear()

        def scan_dir(base_dir: Path):
            result = {}
            for item_dir in base_dir.glob('*'):
                if item_dir.is_dir():
                    key = item_dir.name.lower()
                    result[key] = item_dir
            return result

        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = [executor.submit(scan_dir, dir_path) for dir_path in [POSTER_DIR, COLLECTIONS_DIR]]
            
            # Use as_completed for better memory management
            for future in concurrent.futures.as_completed(futures):
                self.directory_lookup.update(future.result())

            for future in futures:
                self.directory_lookup.update(future.result())

        logger.info(f"Directory scan complete. Found {len(self.directory_lookup)} directories.")

    async def load_items(self):
        """Asynchronously load items from file"""
        try:
            def read_file() -> List[Dict]:
                with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
                    return json.load(f)

            loop = asyncio.get_running_loop()
            self.items_to_process = await loop.run_in_executor(None, read_file)
            logger.info(f"Successfully loaded {len(self.items_to_process)} items.")
        except Exception as e:
            logger.error(f"Error loading items: {str(e)}")
            self.items_to_process = []

    def get_item_directory(self, item: Dict) -> Optional[Path]:
        item_type = item.get('Type', 'Series' if 'Seasons' in item else 'Movie')
        tmdb_id = str(item.get('TMDbId')) if item.get('TMDbId') else None
        
        # Load language data
        try:
            with open(LANGUAGE_DATA_FILENAME, 'r', encoding='utf-8') as f:
                language_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.error(f"Error loading language data from {LANGUAGE_DATA_FILENAME}")
            return None

        # Determine category based on item type
        if item_type == "BoxSet":
            category = "collections"
        elif item_type == "Series":
            category = "tv"
        else:
            category = "movies"

        # Get titles from language data if available
        if tmdb_id and tmdb_id in language_data.get(category, {}):
            item_data = language_data[category][tmdb_id]
            extracted_title = self.clean_name(item_data.get('extracted_title', '').strip())
            original_title = self.clean_name(item_data.get('originaltitle', '').strip())
        else:
            # Fallback to item names if not found in language data
            extracted_title = self.clean_name(item.get('Name', '').strip())
            original_title = self.clean_name(item.get('OriginalTitle', extracted_title).strip())

        item_year = item.get('Year')

        possible_keys = []
        if item_type == "BoxSet":
            possible_keys = [
                extracted_title.lower(),
            ]
        else:
            possible_keys = [
                f"{original_title} ({item_year})".lower(),
                f"{extracted_title} ({item_year})".lower()
            ]

        for key in possible_keys:
            if key in self.directory_cache:
                self.used_folders.append(self.directory_cache[key])
                return self.directory_cache[key]
            elif key in self.directory_lookup:
                self.directory_cache[key] = self.directory_lookup[key]
                self.used_folders.append(self.directory_cache[key])
                return self.directory_cache[key]

        # If we reach here, no directory was found
        base_dir = COLLECTIONS_DIR if item_type == "BoxSet" else POSTER_DIR

        if base_dir == COLLECTIONS_DIR:
            missing_name = f"{original_title}" if original_title and not any(
                ord(char) > 127 for char in original_title) else f"{extracted_title}"
        else:
            missing_name = f"{original_title} ({item_year})" if original_title and not any(
                ord(char) > 127 for char in original_title) else f"{extracted_title} ({item_year})"

        missing_folder = f"Folder not found: {base_dir / missing_name}"
        self.missing_folders.append(missing_folder)
        logger.warning(missing_folder)
        return None

    @staticmethod
    def clean_name(name: str) -> str:
        """Clean filename - now a static method without caching"""
        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '&', "'", '!', '?', '[', ']', '!', '&']
        for char in invalid_chars:
            name = name.replace(char, '')
        return name.strip()

    @staticmethod
    def find_image(item_dir: Path, filename: str) -> Optional[Path]:
        for ext in ['png', 'jpg', 'jpeg', 'webp']:
            image_path = item_dir / f"{filename}.{ext}"
            if image_path.exists():
                return image_path
        return None

    async def delete_all_backdrops(self, item_id: str, item: Dict):
        """Delete all existing backdrop images for an item"""
        try:
            # First get all images for the item
            url = f"{JELLYFIN_URL}/Items/{item_id}/Images"
            headers = {'X-Emby-Token': API_KEY, 'Connection': 'keep-alive'}

            async with self.semaphore:
                async with self.session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    images = await response.json()

                    # Filter for backdrop images
                    backdrop_images = [img for img in images if img.get('ImageType') == 'Backdrop']

                    # Delete each backdrop
                    for image in backdrop_images:
                        delete_url = f"{JELLYFIN_URL}/Items/{item_id}/Images/Backdrop/{image.get('ImageIndex')}"
                        async with self.session.delete(delete_url, headers=headers) as delete_response:
                            delete_response.raise_for_status()
                            logger.debug(f"Deleted backdrop {image.get('ImageIndex')} for {item.get('Name')}")

                    if backdrop_images:
                        logger.info(f"Deleted {len(backdrop_images)} existing backdrops for {item.get('Name')}")

        except Exception as e:
            logger.error(f"Error deleting backdrops for {item.get('Name')}: {str(e)}")

    async def update_jellyfin(self, id: str, image_path: Path, item: Dict, image_type: str = 'Primary',
                             extra_info: str = '', delete_existing: bool = False):
        """Updated update_jellyfin method with delete_existing parameter"""
        try:
            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}. Skipping.")
                return

            # If this is a backdrop and delete_existing is True, delete all existing backdrops first
            if image_type == 'Backdrop' and delete_existing:
                await self.delete_all_backdrops(id, item)

            # Read and encode image
            async with self.semaphore:  # Limit concurrent file operations
                with image_path.open('rb', buffering=1024*1024) as file:  # Buffered reading
                    image_data = file.read()
                encoded_data = b64encode(image_data)

            endpoint = f'/Items/{id}/Images/{image_type}/0'
            url = f"{JELLYFIN_URL}{endpoint}"
            headers = {
                'X-Emby-Token': API_KEY,
                'Content-Type': self.get_content_type(str(image_path)),
                'Connection': 'keep-alive'
            }

            async with self.semaphore:  # Limit concurrent API requests
                async with self.session.post(url, headers=headers, data=encoded_data) as response:
                    response.raise_for_status()
                    display_name = item['Name']
                    log_message = f'Updated {image_type} image for {self.clean_name(display_name)}'
                    if extra_info:
                        log_message += f' - {extra_info}'
                    logger.info(log_message + ' successfully.')

        except Exception as e:
            display_name = item['Name']
            logger.error(
                f'Error updating {image_type} image for {self.clean_name(display_name)}'
                f'{" - " + extra_info if extra_info else ""}. Error: {str(e)}')
        finally:
            del encoded_data
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
        """Process a single item and its related images"""
        try:
            item_dir = self.get_item_directory(item)
            if not item_dir:
                return

            tasks = []

            # Add main poster task
            if (main_poster := self.find_image(item_dir, 'poster')):
                tasks.append(self.update_jellyfin(item['Id'], main_poster, item, 'Primary'))

            # Add backdrop task - check for both 'backdrop' and 'background' with memory-efficient search
            backdrop = self.find_image(item_dir, 'backdrop') or self.find_image(item_dir, 'background')
            if backdrop:
                tasks.append(self.update_jellyfin(
                    item['Id'],
                    backdrop,
                    item,
                    'Backdrop',
                    delete_existing=True
                ))

            # Add season and episode tasks
            if 'Seasons' in item:
                for season_name, season_data in item['Seasons'].items():
                    season_number = season_name.split()[-1]
                    if (season_image := self.find_image(item_dir, f'Season{season_number.zfill(2)}')):
                        tasks.append(self.update_jellyfin(
                            season_data['Id'],
                            season_image,
                            item,
                            'Primary',
                            f'Season {season_number}'
                        ))

                    for episode_number, episode_id in season_data.get('Episodes', {}).items():
                        if (episode_image := self.find_image(
                                item_dir,
                                f'S{season_number.zfill(2)}E{episode_number.zfill(2)}'
                        )):
                            tasks.append(self.update_jellyfin(
                                episode_id,
                                episode_image,
                                item,
                                'Primary',
                                f'S{season_number}E{episode_number}'
                            ))

            if tasks:
                await asyncio.gather(*tasks)

        except Exception as e:
            logger.error(f"Error processing item {item.get('Name', 'Unknown')}: {str(e)}")
        finally:
            gc.collect()

    async def save_missing_folders(self):
        """Save missing and extra folders to their respective files"""
        try:
            # Clear existing files first
            if os.path.exists(MISSING):  # Memory-efficient file handling
                os.remove(MISSING)
            if os.path.exists(EXTRA_FOLDER):
                os.remove(EXTRA_FOLDER)

            all_folders = set()

            all_folders.update(POSTER_DIR.glob('*'))
            gc.collect()

            all_folders.update(COLLECTIONS_DIR.glob('*'))
            gc.collect()

            self.extra_folders = list(all_folders - set(self.used_folders))
            gc.collect()

            # Only create files if there's content to write
            if self.missing_folders:
                with open(MISSING, 'w', encoding='utf-8') as f:
                    for folder in sorted(set(self.missing_folders)):  # Remove duplicates and sort
                        f.write(f"{folder}\n")

            if self.extra_folders:
                with open(EXTRA_FOLDER, 'w', encoding='utf-8') as f:
                    for folder in self.extra_folders:
                        f.write(f"Didn't use Folder: {folder}\n")

            self._log_results()

        except Exception as e:
            logger.error(f"Error in save_missing_folders: {str(e)}")
        finally:
            # Clear the missing_folders list after saving
            self.missing_folders = []
            gc.collect()

    def _log_results(self):
        """Log the results of the missing and extra folders check."""
        missing_exists = os.path.exists(MISSING)  # Minimal file system interactions
        extra_exists = os.path.exists(EXTRA_FOLDER)

        if missing_exists and extra_exists:
            logger.info(f"Saved missing and unused folders to {MISSING} and {EXTRA_FOLDER}")
        elif missing_exists:
            logger.info(f"Saved missing folders to {MISSING}, but no unused folders.")
        elif extra_exists:
            logger.info(f"Saved unused folders to {EXTRA_FOLDER}, but no missing folders.")
        else:
            logger.info("No missing or unused folders to save.")

    async def process_items(self):
        """Process items in parallel batches"""

        # Process items in batches
        for i in range(0, len(self.items_to_process), self.batch_size):
            batch = self.items_to_process[i:i + self.batch_size]
            tasks = [self.process_item(item) for item in batch]
            await asyncio.gather(*tasks)
            gc.collect()

    async def run(self):
        """Main execution method"""
        try:
            await self.initialize()
            time.sleep(1)
            await self.process_items()
            await self.save_missing_folders()
            self.processing_end_time = time.time()
            logger.info(f"Process completed in {self.processing_end_time - self.processing_start_time:.2f} seconds.")
        except Exception as e:
            logger.error(f"Error in run method: {str(e)}")
        finally:
            self.missing_folders = []
            gc.collect()

if __name__ == "__main__":
    updater = UpdateCover()
    asyncio.run(updater.run())
