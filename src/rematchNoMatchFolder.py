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
    """Matches media folders to metadata using exact and fuzzy matching techniques.

    Attributes:
        language_data: Nested dictionary containing media metadata
        title_cache: Preprocessed mapping of normalized titles to media items
        updater: Cover update handler
    """

    def __init__(self, language_data: dict):
        """Initialize with language data and build initial title cache."""
        logger.debug("Initializing FolderMatcher")
        self.language_data = language_data
        self.title_cache = self._build_title_cache()
        self.updater = UpdateCover()
        logger.debug(f"Title cache built with {len(self.title_cache)} entries")

    def update_language_data(self, new_language_data: dict):
        """Refresh metadata and rebuild search cache.

        Args:
            new_language_data: Updated media metadata dictionary
        """
        logger.debug(f"Updating language data with categories: {list(new_language_data.keys())}")
        old_cache_size = len(self.title_cache)
        self.language_data = new_language_data
        self.title_cache = self._build_title_cache()
        new_cache_size = len(self.title_cache)
        logger.debug(f"Title cache updated. Old size: {old_cache_size}, New size: {new_cache_size}")

    def _build_title_cache(self) -> Dict[str, Tuple[str, dict]]:
        """Create normalized title lookup dictionary from metadata.

        Processes movies, TV shows, and collections. Normalizes titles by:
        - Removing parenthetical content (e.g., years)
        - Converting to lowercase

        Returns:
            Dictionary mapping clean titles to (category, metadata) tuples
        """
        cache = {}
        logger.debug("Building title cache")

        # Process different media categories
        for category in ['movies', 'tv', 'collections']:
            category_data = self.language_data.get(category, {})
            if not category_data:
                logger.debug(f"Skipping empty category: {category}")
                continue

            logger.debug(f"Indexing {len(category_data)} {category} items")
            for item_id, item_data in category_data.items():
                if item_id == 'last_updated':  # Skip metadata timestamps
                    continue

                # Aggregate all possible titles
                titles = set(item_data.get('titles', []))
                titles.update({item_data.get('extracted_title'), item_data.get('originaltitle')})
                titles.discard(None)  # Remove any None values from optional fields

                # Normalize and index each title variant
                for title in titles:
                    clean_title = self._clean_title(title)
                    if clean_title:
                        cache[clean_title] = (category, item_data)
                        logger.debug(f"Cached: {clean_title} -> {category}")

        logger.debug(f"Title cache contains {len(cache)} searchable entries")
        return cache

    @staticmethod
    def _clean_title(title: str) -> str:
        """Normalize titles for consistent matching.

        Example:
            "The Matrix (1999)" -> "the matrix"
        """
        # Remove all content within parentheses including whitespace
        clean_name = re.sub(r'\s*\([^)]*\)\s*', '', title)
        return clean_name.lower().strip()

    def find_matching_folder(self, folder_name: str) -> Tuple[bool, Optional[dict]]:
        """Find metadata match for a folder using multi-stage matching.

        Matching process:
        1. Exact match with year verification
        2. Fuzzy match (90%+ similarity) with year verification

        Args:
            folder_name: Raw folder name to match

        Returns:
            Tuple (match_found, matched_metadata)
        """
        logger.debug(f"Matching folder: {folder_name}")

        # Extract publication year if present in folder name
        year_match = re.search(r'\((\d{4})\)', folder_name)
        folder_year = year_match.group(1) if year_match else None
        logger.debug(f"Detected folder year: {folder_year or 'None'}")

        clean_folder = self._clean_title(folder_name)
        logger.debug(f"Normalized folder name: {clean_folder}")

        # Stage 1: Exact title match
        if clean_folder in self.title_cache:
            category, item_data = self.title_cache[clean_folder]
            item_year = str(item_data.get('year', ''))

            if not folder_year or item_year == folder_year:
                logger.debug(f"Exact match in {category} (Year: {item_year})")
                return True, item_data
            logger.debug(f"Year mismatch: {item_year} vs {folder_year}")

        # Stage 2: Fuzzy matching with similarity threshold
        logger.debug("Initiating fuzzy match")
        best_match = process.extractOne(
            clean_folder,
            list(self.title_cache.keys()),
            scorer=fuzz.ratio,
            score_cutoff=90  # Require high confidence match
        )

        if not best_match:
            logger.debug("No qualifying matches found")
            return False, None

        matched_title, score = best_match[0], best_match[1]
        category, item_data = self.title_cache[matched_title]
        logger.debug(f"Fuzzy match: {matched_title} (Score: {score}/100)")

        # Verify year consistency for high-confidence matches
        item_year = str(item_data.get('year', ''))
        if folder_year and item_year != folder_year:
            logger.debug(f"Rejecting match due to year mismatch: {item_year} vs {folder_year}")
            return False, None

        return True, item_data

    def reprocess_unmatched_files(self) -> None:
        """Re-process files in NO_MATCH_FOLDER using current metadata.

        Processing workflow:
        1. Scan Collections/Poster subdirectories
        2. Match series folders to current metadata
        3. Package matched assets into timestamped ZIPs
        4. Dispatch for processing and clean empty folders
        """
        logger.info("Initiating unmatched files reprocessing")

        for media_type in ['Collections', 'Poster']:
            no_match_path = Path(NO_MATCH_FOLDER) / media_type
            if not no_match_path.exists():
                logger.debug(f"Skipping non-existent {media_type} directory")
                continue

            logger.info(f"Processing {media_type} unmatched items")
            series_folders = [f for f in no_match_path.iterdir() if f.is_dir()]
            logger.debug(f"Found {len(series_folders)} candidate folders")

            with ThreadPoolExecutor() as executor:
                for series_folder in series_folders:
                    logger.debug(f"Attempting match for: {series_folder.name}")
                    match_found, metadata = self.find_matching_folder(series_folder.name)

                    if not match_found:
                        logger.debug(f"No current match for {series_folder.name}")
                        continue

                    # Process all versioned subfolders in parallel
                    dated_subfolders = [f for f in series_folder.iterdir() if f.is_dir()]
                    logger.debug(f"Found {len(dated_subfolders)} asset versions")

                    # Prepare parameters for parallel execution
                    task_params = [(subfolder, series_folder.name) for subfolder in dated_subfolders]
                    executor.map(self.process_dated_subfolder, task_params)

                    # Cleanup empty parent folder
                    if not any(series_folder.iterdir()):
                        logger.debug(f"Removing empty series folder: {series_folder}")
                        series_folder.rmdir()

        logger.info("Completed reprocessing cycle")

    def process_dated_subfolder(self, params: Tuple[Path, str]) -> None:
        """Process a versioned asset folder containing multiple files.

        Args:
            params: Tuple containing:
                - Path to dated subfolder
                - Parent series folder name
        """
        dated_subfolder, series_name = params
        logger.debug(f"Processing asset version: {dated_subfolder.name}")

        files = [f for f in dated_subfolder.iterdir() if f.is_file()]
        if not files:
            logger.debug("Skipping empty subfolder")
            return

        # Create unique ZIP filename with rematch identifier
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"{series_name}_{timestamp}_REMATCH_MARKER.zip"
        zip_path = Path(RAW_COVER_DIR) / zip_name

        try:
            # Package files into ZIP archive
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
                for file in files:
                    archive.write(file, file.name)
                    logger.debug(f"Archived: {file.name}")

            logger.info(f"Created rematch package: {zip_path.name}")
            self._process_zip_file(str(zip_path))

            # Cleanup processed files
            for file in files:
                file.unlink()
            logger.debug(f"Cleaned {len(files)} source files")

            # Remove empty subfolder
            if not any(dated_subfolder.iterdir()):
                dated_subfolder.rmdir()
                logger.debug(f"Removed empty directory: {dated_subfolder}")

        except Exception as error:
            logger.error(f"Failed processing {dated_subfolder}: {str(error)}")
            logger.debug(f"Error details:\n{traceback.format_exc()}")

            # Ensure failed ZIPs are cleaned up
            if zip_path.exists():
                zip_path.unlink()

    def _process_zip_file(self, zip_path: str) -> None:
        """Handle ZIP processing through external module with cleanup.

        Special handling for rematch packages:
        - Direct deletion after processing instead of moving to consumed

        Args:
            zip_path: Full path to ZIP file
        """
        try:
            # Import processor dynamically to avoid circular dependencies
            from src.coverCleaner import process_zip_file

            process_zip_file(zip_path, self.language_data)
            logger.debug(f"Completed processing: {zip_path}")

            # Special handling for rematch packages
            if "_REMATCH_MARKER" in zip_path:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    logger.info(f"Removed rematch package: {zip_path}")
            else:
                # Standard processing cleanup
                consumed_path = Path(CONSUMED_DIR) / Path(zip_path).name
                shutil.move(zip_path, consumed_path)
                logger.debug(f"Moved to consumed: {consumed_path.name}")

        except Exception as error:
            logger.error(f"ZIP processing failed: {str(error)}")

            # Ensure failed ZIPs are properly disposed
            if "_REMATCH_MARKER" in zip_path and Path(zip_path).exists():
                Path(zip_path).unlink()
            else:
                shutil.move(zip_path, CONSUMED_DIR)