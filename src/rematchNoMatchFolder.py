from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Tuple, List, Set, Optional
import logging
import zipfile
from datetime import datetime
from fuzzywuzzy import fuzz
import re
import os
import shutil

from src.constants import NO_MATCH_FOLDER, RAW_COVER_DIR, CONSUMED_DIR
from src.updateCover import UpdateCover

logger = logging.getLogger(__name__)


class FolderMatcher:
    def __init__(self, language_data: dict):
        self.language_data = language_data
        self.title_cache = self._build_title_cache()
        self.updater = UpdateCover()

    def _build_title_cache(self) -> Dict[str, Tuple[str, dict]]:
        cache = {}

        for category in ['movies', 'tv', 'collections']:
            category_data = self.language_data.get(category, {})
            if not category_data:
                continue

            for item_id, item_data in category_data.items():
                if item_id == 'last_updated':
                    continue

                # Collect all possible titles
                titles = set(item_data.get('titles', []))
                if 'extracted_title' in item_data:
                    titles.add(item_data['extracted_title'])
                if 'originaltitle' in item_data:
                    titles.add(item_data['originaltitle'])

                # Add each cleaned title to cache
                for title in titles:
                    clean_title = self._clean_title(title)
                    if clean_title:  # Only add non-empty titles
                        cache[clean_title] = (category, item_data)

        return cache

    @staticmethod
    def _clean_title(title: str) -> str:
        # Remove year and common suffixes in one pass
        clean = re.sub(r'\s*\(\d{4}\)|collection$|filmreihe$', '', title, flags=re.IGNORECASE)
        return clean.lower().strip()

    def find_matching_folder(self, folder_name: str) -> Tuple[bool, Optional[dict]]:
        # Extract year if present
        year_match = re.search(r'\((\d{4})\)', folder_name)
        folder_year = year_match.group(1) if year_match else None

        # Clean folder name
        clean_folder = self._clean_title(folder_name)

        # First try exact matches in cache
        if clean_folder in self.title_cache:
            category, item_data = self.title_cache[clean_folder]
            if not folder_year or str(item_data.get('year')) == folder_year:
                return True, item_data

        # If no exact match, try fuzzy matching with threshold
        best_match = None
        best_score = 0

        for cached_title, (category, item_data) in self.title_cache.items():
            score = fuzz.ratio(clean_folder, cached_title)

            if score > best_score and score >= 90:
                if not folder_year or str(item_data.get('year')) == folder_year:
                    best_score = score
                    best_match = item_data

        return bool(best_match), best_match

    def process_dated_subfolder(self, params: Tuple[Path, str]) -> None:
        dated_subfolder, series_name = params

        # Skip if empty
        files_to_process = [f for f in dated_subfolder.iterdir() if f.is_file()]
        if not files_to_process:
            return

        # Create zip file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"{series_name}_{timestamp}.zip"
        zip_path = Path(RAW_COVER_DIR) / zip_filename

        try:
            # Create zip file with all images
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in files_to_process:
                    zipf.write(file, file.name)
                    logger.debug(f"Added {file.name} to {zip_filename}")

            # Process the zip file
            self._process_zip_file(str(zip_path))

            # Clean up processed files
            for file in files_to_process:
                file.unlink()
                logger.debug(f"Removed processed file: {file}")

            # Remove empty subfolder
            if not any(dated_subfolder.iterdir()):
                dated_subfolder.rmdir()
                logger.debug(f"Removed empty dated subfolder: {dated_subfolder}")

        except Exception as e:
            logger.error(f"Error processing subfolder {dated_subfolder}: {str(e)}")

    def _process_zip_file(self, zip_path: str) -> None:
        try:
            from src.coverCleaner import process_zip_file
            process_zip_file(zip_path, self.language_data)

            # Move processed zip to consumed
            if os.path.exists(zip_path):
                consumed_path = os.path.join(CONSUMED_DIR, os.path.basename(zip_path))
                shutil.move(zip_path, consumed_path)

        except Exception as e:
            logger.error(f"Error processing ZIP file {zip_path}: {str(e)}")
            # Ensure zip file is moved to consumed even if processing fails
            if os.path.exists(zip_path):
                consumed_path = os.path.join(CONSUMED_DIR, os.path.basename(zip_path))
                shutil.move(zip_path, consumed_path)

    def reprocess_unmatched_files(self) -> None:
        """
        Reprocess unmatched files with optimized matching and parallel processing.
        """
        logger.info("Starting reprocessing of unmatched files")

        # Process each subfolder type
        for subfolder in ['Collections', 'Poster']:
            no_match_path = Path(NO_MATCH_FOLDER) / subfolder
            if not no_match_path.exists():
                continue

            # Get all series folders
            series_folders = [f for f in no_match_path.iterdir() if f.is_dir()]

            # Process series folders in parallel
            with ThreadPoolExecutor() as executor:
                for series_folder in series_folders:
                    has_match, matched_item = self.find_matching_folder(series_folder.name)

                    if not has_match:
                        continue

                    # Get all dated subfolders
                    dated_subfolders = [f for f in series_folder.iterdir() if f.is_dir()]
                    if not dated_subfolders:
                        continue

                    # Process dated subfolders in parallel
                    params = [(subfolder, series_folder.name) for subfolder in dated_subfolders]
                    executor.map(self.process_dated_subfolder, params)

                    # Remove empty series folder
                    if not any(series_folder.iterdir()):
                        series_folder.rmdir()
                        logger.debug(f"Removed empty series folder: {series_folder}")

        logger.info("Finished reprocessing unmatched files")
