# Standard library imports
import asyncio
import json
import logging
import os
import time
import gc
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from pathlib import Path
from typing import Dict, List, Optional

# Third-party imports
import aiohttp
import hashlib

# Local imports
from src.config import JELLYFIN_URL, API_KEY, TMDB_KEY, BATCH_SIZE
from src.constants import (
    POSTER_DIR,
    COLLECTIONS_DIR,
    OUTPUT_FILENAME,
    MISSING,
    EXTRA_FOLDER,
    LANGUAGE_DATA_FILENAME
)

# Initialize logger for the module
logger = logging.getLogger(__name__)


class UpdateCover:
    """Class to handle updating cover images in Jellyfin"""

    # Class variables
    _file_cache = {}  # Cache for file existence checks

    def __init__(self):
        # Core attributes
        self.directory_lookup: Dict[str, Path] = {}
        self.used_folders: List[Path] = []
        self.missing_folders: List[str] = []
        self.extra_folders: List[Path] = []
        self.items_to_process: List[Dict] = []
        self._language_data = None  # Cache for language data

        # Session and timing
        self.session: Optional[aiohttp.ClientSession] = None
        self.processing_start_time = None
        self.processing_end_time = None

        # Performance settings
        self.semaphore = asyncio.Semaphore(20)  # Limit concurrent requests
        self.batch_size = BATCH_SIZE  # Number of items to process in parallel
        self._image_cache = {}  # Cache for image hashes
        self._missing_folders_cache = set()  # Cache for missing folders
        self._executor = None  # Initialize as None, create when needed

    # Context Management Methods
    async def __aenter__(self):
        # Initialize HTTP session
        self.session = aiohttp.ClientSession()
        # Clear all caches before starting a new run
        logger.debug("Clearing all caches before starting new run")
        self.directory_cache.clear()
        self._image_cache.clear()
        self._missing_folders_cache.clear()
        UpdateCover._file_cache.clear()  # Clear the class-level file cache
        self._language_data = None
        # Create new executor if needed
        if self._executor is None or self._executor._shutdown:
            self._executor = ThreadPoolExecutor(max_workers=os.cpu_count())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Clean up resources
        if self.session:
            logger.debug("Cleaning up resources in __aexit__")
            if self._executor and not self._executor._shutdown:
                self._executor.shutdown(wait=False)
            gc.collect()
            await self.session.close()

    @cached_property
    def directory_cache(self):
        """Lazy-loaded directory cache"""
        return {}

    # File System Operations
    @staticmethod
    def clean_name(name: str) -> str:
        """Clean filename by removing invalid characters"""
        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '&', "'", '!', '?', '[', ']', '!', '&']
        for char in invalid_chars:
            name = name.replace(char, '')
        return name.strip()

    @staticmethod
    def find_image(item_dir: Path, filename: str) -> Optional[Path]:
        """Find image file with improved caching"""
        if not item_dir or not item_dir.name:
            return None

        cache_key = f"{item_dir.name.lower()}_{filename.lower()}"
        for ext in ['png', 'jpg', 'jpeg', 'webp']:
            full_cache_key = f"{cache_key}_{ext}"
            if full_cache_key in UpdateCover._file_cache:
                image_path = UpdateCover._file_cache[full_cache_key]
                if image_path.exists():
                    return image_path
        return None

    @staticmethod
    def get_content_type(file_path: str) -> str:
        """Get content type based on file extension"""
        ext = file_path.split('.')[-1].lower()
        return {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'webp': 'image/webp'
        }.get(ext, 'application/octet-stream')

    # Directory Management
    def scan_directories(self):
        """Scan directories using parallel processing with improved caching"""
        logger.info("Scanning directories...")
        self.directory_lookup.clear()

        # Only clear file cache if it's empty or if we're starting fresh
        if not UpdateCover._file_cache:
            logger.debug("File cache is empty, no need to clear")
        else:
            logger.debug("Clearing file cache before scanning")
            UpdateCover._file_cache.clear()

        def scan_dir(base_dir: Path):
            result = {}
            try:
                for item_dir in base_dir.glob('*'):
                    if item_dir.is_dir():
                        key = item_dir.name.lower()
                        result[key] = item_dir
                        # Cache all image files in the directory
                        for ext in ['png', 'jpg', 'jpeg', 'webp']:
                            for img_file in item_dir.glob(f"*.{ext}"):
                                try:
                                    cache_key = f"{key}_{img_file.stem}_{ext}"
                                    UpdateCover._file_cache[
                                        cache_key] = img_file.resolve()  # Use resolve() to get absolute path
                                except Exception as e:
                                    logger.warning(f"Error caching file {img_file}: {str(e)}")
            except Exception as e:
                logger.error(f"Error scanning directory {base_dir}: {str(e)}")
            return result

        try:
            futures = [self._executor.submit(scan_dir, dir_path) for dir_path in [POSTER_DIR, COLLECTIONS_DIR]]
            for future in futures:
                self.directory_lookup.update(future.result())
        except Exception as e:
            logger.error(f"Error in scan_directories: {str(e)}")
            raise

        logger.info(f"Directory scan complete. Found {len(self.directory_lookup)} directories.")
        logger.debug(f"File cache populated with {len(UpdateCover._file_cache)} entries")

    def _load_language_data(self):
        """Load and cache language data"""
        if self._language_data is None:
            try:
                with open(LANGUAGE_DATA_FILENAME, 'r', encoding='utf-8') as f:
                    self._language_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                logger.error(f"Error loading language data from {LANGUAGE_DATA_FILENAME}")
                self._language_data = {}

    def get_item_directory(self, item: Dict) -> Optional[Path]:
        """Find the directory for a given item based on its metadata"""
        item_type = item.get('Type', 'Series' if 'Seasons' in item else 'Movie')
        tmdb_id = str(item.get('TMDbId')) if item.get('TMDbId') else None

        # Load language data if not cached
        self._load_language_data()

        # Determine category and get titles
        category = "collections" if item_type == "BoxSet" else "tv" if item_type == "Series" else "movies"

        if tmdb_id and tmdb_id in self._language_data.get(category, {}):
            item_data = self._language_data[category][tmdb_id]
            extracted_title = self.clean_name(item_data.get('extracted_title', '').strip())
            original_title = self.clean_name(item_data.get('originaltitle', '').strip())
            english_title = self.clean_name(item_data.get('english_title', '').strip())
        else:
            extracted_title = self.clean_name(item.get('Name', '').strip())
            original_title = self.clean_name(item.get('OriginalTitle', extracted_title).strip())
            english_title = extracted_title

        item_year = item.get('Year')
        possible_keys = (
            [extracted_title.lower()] if item_type == "BoxSet"
            else [
                f"{original_title} ({item_year})".lower(),
                f"{extracted_title} ({item_year})".lower()
            ]
        )

        # Check cache and lookup
        for key in possible_keys:
            if key in self.directory_cache:
                self.used_folders.append(self.directory_cache[key])
                return self.directory_cache[key]
            elif key in self.directory_lookup:
                self.directory_cache[key] = self.directory_lookup[key]
                self.used_folders.append(self.directory_cache[key])
                return self.directory_cache[key]

        # Handle missing directory
        base_dir = COLLECTIONS_DIR if item_type == "BoxSet" else POSTER_DIR
        missing_name = self._get_missing_name(english_title, extracted_title, item_year, item_type == "BoxSet")
        missing_folder = f"Folder not found: {base_dir / missing_name}"

        # Only add to missing folders if not already in cache
        if missing_folder not in self._missing_folders_cache:
            self._missing_folders_cache.add(missing_folder)
            self.missing_folders.append(missing_folder)
            logger.warning(missing_folder)

        return None

    @staticmethod
    def _get_missing_name(english_title: str, extracted_title: str, item_year: str, is_collection: bool) -> str:
        """Helper method to generate missing folder name"""
        use_english = english_title and not any(ord(char) > 127 for char in english_title)
        if is_collection:
            return english_title if use_english else extracted_title
        return f"{english_title} ({item_year})" if use_english else f"{extracted_title} ({item_year})"

    # Jellyfin API Operations
    async def delete_all_backdrops(self, item_id: str, item: Dict):
        """Delete all existing backdrop images for an item"""
        try:
            url = f"{JELLYFIN_URL}/Items/{item_id}/Images"
            headers = {'X-Emby-Token': API_KEY, 'Connection': 'keep-alive'}

            async with self.semaphore:
                async with self.session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    images = await response.json()
                    backdrop_images = [img for img in images if img.get('ImageType') == 'Backdrop']

                    for image in backdrop_images:
                        delete_url = f"{JELLYFIN_URL}/Items/{item_id}/Images/Backdrop/{image.get('ImageIndex')}"
                        async with self.session.delete(delete_url, headers=headers) as delete_response:
                            delete_response.raise_for_status()
                            logger.debug(f"Deleted backdrop {image.get('ImageIndex')} for {item.get('Name')}")

                    if backdrop_images:
                        logger.info(f"Deleted {len(backdrop_images)} existing backdrops for {item.get('Name')}")

        except Exception as e:
            logger.error(f"Error deleting backdrops for {item.get('Name')}: {str(e)}")

    async def get_jellyfin_image_hash(self, item_id: str, image_type: str = 'Primary', index: int = 0) -> Optional[str]:
        """Get hash of the current image on Jellyfin server"""
        try:
            url = f"{JELLYFIN_URL}/Items/{item_id}/Images/{image_type}/{index}"
            headers = {'X-Emby-Token': API_KEY, 'Connection': 'keep-alive'}

            async with self.semaphore:
                async with self.session.get(url, headers=headers) as response:
                    if response.status == 404:
                        return None  # Image doesn't exist

                    response.raise_for_status()
                    image_data = await response.read()
                    return self.calculate_hash(image_data)
        except Exception as e:
            logger.debug(f"Error getting image hash from Jellyfin: {str(e)}")
            return None

    def calculate_hash(self, data: bytes) -> str:
        """Calculate a simple hash of image data"""
        import hashlib
        return hashlib.md5(data).hexdigest()

    def get_local_image_hash(self, image_path: Path) -> Optional[str]:
        """Get hash of a local image file"""
        try:
            if not image_path.exists():
                return None

            with image_path.open('rb') as f:
                data = f.read()
                return self.calculate_hash(data)
        except Exception as e:
            logger.debug(f"Error calculating hash for {image_path}: {str(e)}")
            return None

    async def are_images_identical(self, item_id: str, image_path: Path, image_type: str = 'Primary') -> bool:
        """Compare if the local image is identical to the one on Jellyfin"""
        if not image_path.exists():
            return False

        jellyfin_hash = await self.get_jellyfin_image_hash(item_id, image_type)
        if not jellyfin_hash:
            return False  # Image doesn't exist on Jellyfin or error occurred

        local_hash = self.get_local_image_hash(image_path)
        if not local_hash:
            return False  # Error reading local file

        return jellyfin_hash == local_hash

    async def update_jellyfin(self, id: str, image_path: Path, item: Dict, image_type: str = 'Primary',
                              extra_info: str = '', delete_existing: bool = False):
        """Update image in Jellyfin only if needed"""
        try:
            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}. Skipping.")
                return

            # Use cached hash if available
            cache_key = f"{id}_{image_type}"
            if cache_key in self._image_cache:
                identical = self._image_cache[cache_key]
            else:
                identical = await self.are_images_identical(id, image_path, image_type)
                self._image_cache[cache_key] = identical

            if identical:
                logger.info(f"Image {image_type} for {item.get('Name')} - {extra_info} unchanged. Skipping upload.")
                return

            if image_type == 'Backdrop' and delete_existing:
                await self.delete_all_backdrops(id, item)

            # Read file in chunks to reduce memory usage
            chunk_size = 1024 * 1024  # 1MB chunks
            chunks = []
            async with self.semaphore:
                with image_path.open('rb', buffering=1024 * 1024) as file:
                    image_data = file.read()
                encoded_data = b64encode(image_data)

            url = f"{JELLYFIN_URL}/Items/{id}/Images/{image_type}/0"
            headers = {
                'X-Emby-Token': API_KEY,
                'Content-Type': self.get_content_type(str(image_path)),
                'Connection': 'keep-alive'
            }

            async with self.semaphore:
                async with self.session.post(url, headers=headers, data=encoded_data) as response:
                    response.raise_for_status()
                    self._log_success(item['Name'], image_type, extra_info)

        except Exception as e:
            self._log_error(item['Name'], image_type, extra_info, str(e))
        finally:
            if 'encoded_data' in locals():
                del encoded_data
                gc.collect()

    # Processing Methods
    async def process_item(self, item: Dict):
        """Process a single item's images"""
        try:
            item_dir = self.get_item_directory(item)
            if not item_dir:
                return

            tasks = []
            self._add_tasks(item, item_dir, tasks)

            if tasks:
                await asyncio.gather(*tasks)

        except Exception as e:
            logger.error(f"Error processing item {item.get('Name', 'Unknown')}: {str(e)}")
        finally:
            gc.collect()

    def _add_tasks(self, item: Dict, item_dir: Path, tasks: List):
        """Add tasks for all image types"""
        # Main images
        for img_type, names in {
            'Primary': ['poster'],
            'Backdrop': ['backdrop', 'background']
        }.items():
            if img := next((self.find_image(item_dir, name) for name in names if self.find_image(item_dir, name)),
                           None):
                tasks.append(
                    self.update_jellyfin(item['Id'], img, item, img_type, delete_existing=img_type == 'Backdrop'))

        # Season & Episode images
        if 'Seasons' not in item:
            return

        for season_name, season_data in item['Seasons'].items():
            season_num = season_name.split()[-1].zfill(2)

            # Season poster
            if season_img := self.find_image(item_dir, f'Season{season_num}'):
                tasks.append(
                    self.update_jellyfin(season_data['Id'], season_img, item, 'Primary', f'Season {int(season_num)}'))

            # Episode images
            for ep_num, ep_id in season_data.get('Episodes', {}).items():
                if ep_img := self.find_image(item_dir, f'S{season_num}E{ep_num.zfill(2)}'):
                    tasks.append(
                        self.update_jellyfin(ep_id, ep_img, item, 'Primary', f'S{int(season_num)}E{int(ep_num)}'))

    # Initialization and Main Execution
    async def initialize(self):
        """Initialize the update process"""
        self.missing_folders = []
        # Ensure executor is initialized
        if self._executor is None or self._executor._shutdown:
            self._executor = ThreadPoolExecutor(max_workers=os.cpu_count())
        self.scan_directories()
        self.processing_start_time = time.time()

        await self.load_items()
        logger.info(
            f"Initialization complete. Found {len(self.directory_lookup)} directories and {len(self.items_to_process)} items to process.")

    async def load_items(self):
        """Load items from JSON file with improved error handling"""
        try:
            def read_file() -> List[Dict]:
                with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
                    return json.load(f)

            loop = asyncio.get_running_loop()
            self.items_to_process = await loop.run_in_executor(None, read_file)

            # Pre-process items for better performance
            for item in self.items_to_process:
                if 'Seasons' in item:
                    for season_data in item['Seasons'].values():
                        if 'Episodes' in season_data:
                            season_data['Episodes'] = {
                                k: v for k, v in season_data['Episodes'].items()
                                if isinstance(k, str) and k.isdigit()
                            }

            logger.info(f"Successfully loaded {len(self.items_to_process)} items.")
        except Exception as e:
            logger.error(f"Error loading items: {str(e)}")
            self.items_to_process = []

    async def process_items(self):
        """Process items in optimized batches with improved memory management"""
        tasks = []
        for item in self.items_to_process:
            tasks.append(self.process_item(item))
            if len(tasks) >= self.batch_size:
                await asyncio.gather(*tasks)
                tasks = []
                gc.collect()

        if tasks:
            await asyncio.gather(*tasks)
        gc.collect()

    async def run(self):
        """Main execution method"""
        try:
            await self.initialize()
            await self.process_items()
            await self.save_missing_folders()
            self.processing_end_time = time.time()
            logger.info(f"Process completed in {self.processing_end_time - self.processing_start_time:.2f} seconds.")
        except Exception as e:
            logger.error(f"Error in run method: {str(e)}")
        finally:
            self.missing_folders = []
            gc.collect()

    # Logging and Results
    def _log_success(self, name: str, image_type: str, extra_info: str):
        """Log successful image update"""
        log_message = f'Updated {image_type} image for {self.clean_name(name)}'
        if extra_info:
            log_message += f' - {extra_info}'
        logger.info(log_message + ' successfully.')

    def _log_error(self, name: str, image_type: str, extra_info: str, error: str):
        """Log image update error"""
        logger.error(
            f'Error updating {image_type} image for {self.clean_name(name)}'
            f'{" - " + extra_info if extra_info else ""}. Error: {error}'
        )

    async def save_missing_folders(self):
        """Save missing and extra folders with improved performance"""
        try:
            # Clear existing files
            for file_path in [MISSING, EXTRA_FOLDER]:
                if os.path.exists(file_path):
                    os.remove(file_path)

            # Collect all folders in parallel
            def collect_folders():
                all_folders = set()
                all_folders.update(POSTER_DIR.glob('*'))
                all_folders.update(COLLECTIONS_DIR.glob('*'))
                return all_folders

            all_folders = await asyncio.get_running_loop().run_in_executor(
                self._executor, collect_folders)

            # Find extra folders
            self.extra_folders = list(all_folders - set(self.used_folders))

            # Save files in parallel
            save_tasks = []
            if self.missing_folders:
                save_tasks.append(self._save_file(MISSING, sorted(set(self.missing_folders))))
            if self.extra_folders:
                save_tasks.append(self._save_file(EXTRA_FOLDER, self.extra_folders))

            if save_tasks:
                await asyncio.gather(*save_tasks)

            self._log_results()

        except Exception as e:
            logger.error(f"Error in save_missing_folders: {str(e)}")
        finally:
            self.missing_folders = []
            gc.collect()

    async def _save_file(self, file_path: str, data: List[str]):
        """Helper method to save file asynchronously"""

        def write_file():
            with open(file_path, 'w', encoding='utf-8') as f:
                for item in data:
                    f.write(f"{item}\n")

        await asyncio.get_running_loop().run_in_executor(self._executor, write_file)

    def _log_results(self):
        """Log results of folder analysis"""
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
