import os
import logging
from pathlib import Path
from src.constants import NO_MATCH_FOLDER

logger = logging.getLogger(__name__)


def cleanup_empty_folders(start_path: Path = Path(NO_MATCH_FOLDER)) -> None:

    if not start_path.exists():
        logger.debug(f"Path does not exist: {start_path}")
        return

    try:
        # Convert to Path object if string was passed
        start_path = Path(start_path)

        # Traverse the directory tree bottom-up
        for dirpath, dirnames, filenames in os.walk(str(start_path), topdown=False):
            current_dir = Path(dirpath)

            # Skip if this is the NO_MATCH_FOLDER root directory
            if current_dir == Path(NO_MATCH_FOLDER):
                continue

            try:
                # Check if directory is empty (no files and no non-empty subdirectories)
                is_empty = True
                for item in current_dir.iterdir():
                    if item.is_file():
                        is_empty = False
                        break
                    if item.is_dir():
                        # If there are any remaining subdirectories, the folder is not empty
                        if any(item.iterdir()):
                            is_empty = False
                            break

                if is_empty:
                    logger.info(f"Removing empty directory: {current_dir}")
                    current_dir.rmdir()
            except Exception as e:
                logger.error(f"Error processing directory {current_dir}: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Error during empty folder cleanup: {str(e)}")