from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Tuple, List, Set, Optional
import logging
import zipfile
from datetime import datetime
from rapidfuzz import fuzz, process
import re
import os
import shutil
import traceback

from src.constants import NO_MATCH_FOLDER, RAW_COVER_DIR, CONSUMED_DIR
from src.updateCover import UpdateCover

logger = logging.getLogger(__name__)


class FolderMatcher:
    def __init__(self, language_data: dict):
        logger.debug("Initializing FolderMatcher")
        self.language_data = language_data
        self.title_cache = self._build_title_cache()
        self.updater = UpdateCover()
        logger.debug(f"Title cache built with {len(self.title_cache)} entries")

    def update_language_data(self, new_language_data: dict):
        """Update language data and rebuild the title cache."""
        logger.debug(f"Updating language data with categories: {list(new_language_data.keys())}")
        logger.debug(f"Collections in new data: {len(new_language_data.get('collections', {}))}")
        old_cache_size = len(self.title_cache)
        self.language_data = new_language_data
        self.title_cache = self._build_title_cache()
        new_cache_size = len(self.title_cache)
        logger.debug(f"Title cache updated. Old size: {old_cache_size}, New size: {new_cache_size}")
        logger.debug(f"Cache difference: {new_cache_size - old_cache_size} entries")

    def _build_title_cache(self) -> Dict[str, Tuple[str, dict]]:
        cache = {}
        logger.debug("Building title cache")

        for category in ['movies', 'tv', 'collections']:
            category_data = self.language_data.get(category, {})
            if not category_data:
                logger.debug(f"No data found for category: {category}")
                continue

            logger.debug(f"Processing {category} with {len(category_data)} items")
            for item_id, item_data in category_data.items():
                if item_id == 'last_updated':
                    continue

                titles = set(item_data.get('titles', []))
                if 'extracted_title' in item_data:
                    titles.add(item_data['extracted_title'])
                if 'originaltitle' in item_data:
                    titles.add(item_data['originaltitle'])

                logger.debug(f"Found {len(titles)} titles for item {item_id}")

                for title in titles:
                    clean_title = self._clean_title(title)
                    if clean_title:
                        cache[clean_title] = (category, item_data)
                        logger.debug(f"Added to cache: {clean_title} -> {category}")

        logger.debug(f"Title cache built with {len(cache)} total entries")
        return cache

    @staticmethod
    def _clean_title(title: str) -> str:
        # Remove all parenthetical content (including years and empty parentheses)
        clean_name = re.sub(r'\s*\([^)]*\)\s*', '', title)
        return clean_name.lower().strip()

    def find_matching_folder(self, folder_name: str) -> Tuple[bool, Optional[dict]]:
        logger.debug(f"Attempting to match folder: {folder_name}")

        # Extract year if present
        year_match = re.search(r'\((\d{4})\)', folder_name)
        folder_year = year_match.group(1) if year_match else None
        if folder_year:
            logger.debug(f"Extracted year from folder name: {folder_year}")

        # Clean folder name
        clean_folder = self._clean_title(folder_name)
        logger.debug(f"Cleaned folder name: {clean_folder}")

        # First try exact matches in cache
        if clean_folder in self.title_cache:
            category, item_data = self.title_cache[clean_folder]
            if not folder_year or str(item_data.get('year')) == folder_year:
                logger.debug(f"Found exact match in category {category}")
                return True, item_data
            else:
                logger.debug("Found title match but year mismatch")

        # If no exact match, try fuzzy matching using RapidFuzz
        logger.debug("No exact match found, trying fuzzy matching")

        # Get all cached titles as a list for process.extractOne
        cached_titles = list(self.title_cache.keys())

        # Use RapidFuzz's process.extractOne for efficient matching
        best_match = process.extractOne(
            clean_folder,
            cached_titles,
            scorer=fuzz.ratio,
            score_cutoff=90
        )

        if best_match:
            matched_title, score = best_match[0], best_match[1]
            category, item_data = self.title_cache[matched_title]

            logger.debug(f"Found fuzzy match: {matched_title} with score {score}")

            # Check year if present
            if not folder_year or str(item_data.get('year')) == folder_year:
                logger.debug("Year matches or not specified")
                return True, item_data
            else:
                logger.debug("Year mismatch in fuzzy match")
                return False, None
        else:
            logger.debug("No suitable match found")
            return False, None

    def reprocess_unmatched_files(self) -> None:
        logger.info("Starting reprocessing of unmatched files")

        # Process each subfolder type
        for subfolder in ['Collections', 'Poster']:
            no_match_path = Path(NO_MATCH_FOLDER) / subfolder
            if not no_match_path.exists():
                logger.debug(f"No match folder does not exist: {no_match_path}")
                continue

            logger.debug(f"Processing subfolder: {subfolder}")

            # Get all series folders
            series_folders = [f for f in no_match_path.iterdir() if f.is_dir()]
            logger.debug(f"Found {len(series_folders)} series folders in {subfolder}")

            # Process series folders in parallel
            with ThreadPoolExecutor() as executor:
                for series_folder in series_folders:
                    logger.debug(f"Attempting to match series folder: {series_folder.name}")
                    has_match, matched_item = self.find_matching_folder(series_folder.name)

                    if not has_match:
                        logger.debug(f"No match found for folder: {series_folder.name}")
                        continue
                    else:
                        logger.debug(f"Match found for folder: {series_folder.name}")

                    # Get all dated subfolders
                    dated_subfolders = [f for f in series_folder.iterdir() if f.is_dir()]
                    if not dated_subfolders:
                        logger.debug(f"No dated subfolders found in {series_folder.name}")
                        continue

                    logger.debug(f"Processing {len(dated_subfolders)} dated subfolders for {series_folder.name}")

                    # Process dated subfolders in parallel
                    params = [(subfolder, series_folder.name) for subfolder in dated_subfolders]
                    executor.map(self.process_dated_subfolder, params)

                    # Remove empty series folder
                    if not any(series_folder.iterdir()):
                        logger.debug(f"Removing empty series folder: {series_folder}")
                        series_folder.rmdir()

        logger.info("Finished reprocessing unmatched files")

    def process_dated_subfolder(self, params: Tuple[Path, str]) -> None:
        dated_subfolder, series_name = params
        logger.debug(f"Processing dated subfolder: {dated_subfolder} for series: {series_name}")

        # Skip if empty
        files_to_process = [f for f in dated_subfolder.iterdir() if f.is_file()]
        if not files_to_process:
            logger.debug(f"No files to process in {dated_subfolder}")
            return

        logger.debug(f"Found {len(files_to_process)} files to process")

        # Create zip file with special rematch marker
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"{series_name}_{timestamp}_REMATCH_MARKER.zip"
        zip_path = Path(RAW_COVER_DIR) / zip_filename

        logger.debug(f"Creating zip file: {zip_filename}")

        try:
            # Create zip file with all images
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in files_to_process:
                    zipf.write(file, file.name)
                    logger.debug(f"Added {file.name} to {zip_filename}")

            logger.debug(f"Created zip file successfully: {zip_path}")

            # Process the zip file
            logger.debug(f"Starting to process zip file: {zip_path}")
            self._process_zip_file(str(zip_path))

            # Clean up processed files
            for file in files_to_process:
                logger.debug(f"Removing processed file: {file}")
                file.unlink()

            # Remove empty subfolder
            if not any(dated_subfolder.iterdir()):
                logger.debug(f"Removing empty dated subfolder: {dated_subfolder}")
                dated_subfolder.rmdir()

        except Exception as e:
            logger.error(f"Error processing subfolder {dated_subfolder}: {str(e)}")
            logger.debug(f"Stack trace: {traceback.format_exc()}")

    def _process_zip_file(self, zip_path: str) -> None:
        try:
            from src.coverCleaner import process_zip_file
            process_zip_file(zip_path, self.language_data)

            # Delete the zip file directly if it's a rematch
            if "_REMATCH_MARKER" in zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
                logger.info(f"Deleted rematch zip file: {zip_path}")
            else:
                # Move to consumed only if it's not a rematch
                if os.path.exists(zip_path):
                    consumed_path = os.path.join(CONSUMED_DIR, os.path.basename(zip_path))
                    shutil.move(zip_path, consumed_path)

        except Exception as e:
            logger.error(f"Error processing ZIP file {zip_path}: {str(e)}")
            # Clean up zip file even if processing fails
            if "_REMATCH_MARKER" in zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
            elif os.path.exists(zip_path):
                consumed_path = os.path.join(CONSUMED_DIR, os.path.basename(zip_path))
                shutil.move(zip_path, consumed_path)