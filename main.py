import asyncio
import os
import logging
import argparse
import traceback

from src.coverCleaner import cover_cleaner, reprocess_unmatched_files
from src.getIDs import get_jellyfin_content
from src.detectContentChange import check_jellyfin_content
from src.logging import setup_logging
from src.updateCover import UpdateCover
from src.languageLookup import collect_titles
from src.blacklist import update_output_file
from src.constants import RAW_COVER_DIR, MEDIUX_FILE
from src.mediux_downloader import mediux_downloader

logger = logging.getLogger(__name__)


async def main_loop(force: bool):
    updater = UpdateCover()

    while True:
        try:
            RAW_COVER_DIR.mkdir(parents=True, exist_ok=True)

            # Initialize mediux as False
            mediux = False

            if os.path.exists(MEDIUX_FILE):
                with open(MEDIUX_FILE, 'r') as file:
                    content = file.read().rstrip()
                    # Set mediux to True if content is not empty
                    mediux = bool(content)
            else:
                with open(MEDIUX_FILE, 'w'):
                    pass

            files = os.listdir(RAW_COVER_DIR)
            content_changed = check_jellyfin_content()

            # Check if there are any files or new jellyfin content
            if files or content_changed or force or mediux:
                logging.info('Found files, new Jellyfin content, or --force flag set!')
                if content_changed or force:
                    get_jellyfin_content()
                    collect_titles()
                    update_output_file()
                if files or mediux:
                    if mediux:
                        await mediux_downloader()
                    cover_cleaner()
                    mediux = False

                # Load language data
                from src.coverCleaner import load_language_data
                language_data = load_language_data()

                # Reprocess unmatched files
                reprocess_unmatched_files(language_data)

                if force:
                    logging.info("Force flag was set, resetting it to False after first iteration.")
                    force = False
                updater.scan_directories()
                logging.info('Run the UpdateCover process')
                await updater.run()
            else:
                logging.info('Found no files or new content on Jellyfin')

            await asyncio.sleep(30)  # Wait for 30 seconds before the next iteration
        except Exception as e:
            logger.error(f"An error occurred in the main loop: {str(e)}")
            logger.error(traceback.format_exc())
            await asyncio.sleep(60)  # Wait for 1 minute before retrying if an error occurs


if __name__ == "__main__":
    setup_logging()

    # Argument parser
    parser = argparse.ArgumentParser(description="Cover cleaner with optional force update.")
    parser.add_argument('--force', action='store_true', help="Force the process to run regardless of conditions.")
    args = parser.parse_args()

    try:
        asyncio.run(main_loop(args.force))
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Shutting down.")
    except Exception as e:
        logger.critical(f"Critical error occurred: {str(e)}")
        logger.critical(traceback.format_exc())