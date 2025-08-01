import asyncio
import os
import logging
import argparse
import time
import traceback
import gc
import datetime
from typing import Optional

from src.coverCleaner import cover_cleaner, load_language_data, consolidate_series_folders
from src.getIDs import get_jellyfin_content
from src.detectContentChange import check_jellyfin_content
from src.logging import setup_logging
from src.updateCover import UpdateCover
from src.languageLookup import collect_titles
from src.blacklist import update_output_file
from src.constants import RAW_COVER_DIR, MEDIUX_FILE, COVER_DIR
from src.mediux_downloader import mediux_downloader
from src.webhook import WebhookServer
from src.config import ENABLE_WEBHOOK
from src.rematchNoMatchFolder import FolderMatcher
from src.cleanupEmptyFolder import cleanup_empty_folders
from src.scheduler import get_next_scheduled_time, is_scheduled_time, format_time_until_next, SCHEDULED_TIMES

logger = logging.getLogger(__name__)

async def main_loop(force: bool, webhook_server: WebhookServer):
    updater = UpdateCover()
    folder_matcher = None
    last_check_minute: Optional[int] = None

    while True:
        try:
            current_minute = datetime.datetime.now().minute

            # Check for scheduled execution once per minute
            schedule_triggered = False
            if current_minute != last_check_minute:
                schedule_triggered = is_scheduled_time()
                last_check_minute = current_minute

            RAW_COVER_DIR.mkdir(parents=True, exist_ok=True)

            mediux = False
            if os.path.exists(MEDIUX_FILE):
                with open(MEDIUX_FILE, 'r') as file:
                    content = file.read().rstrip()
                    mediux = bool(content)
            else:
                with open(MEDIUX_FILE, 'w'):
                    pass

            files = os.listdir(RAW_COVER_DIR)

            if len(files) == 1 and files[0] == '.DS_Store':
                files = False

            content_changed = check_jellyfin_content()
            webhook_triggered = webhook_server.get_trigger_status() if ENABLE_WEBHOOK else False

            if files or content_changed or force or mediux or webhook_triggered or schedule_triggered:
                if schedule_triggered:
                    logging.info('Process triggered by scheduled time!')
                elif webhook_triggered:
                    logging.info('Process triggered by webhook!')
                else:
                    logging.info('Found files, new Jellyfin content, or --force flag set!')

                get_jellyfin_content()
                update_output_file()
                collect_titles()

                language_data = load_language_data()

                if folder_matcher is None:
                    folder_matcher = FolderMatcher(language_data)
                else:
                    folder_matcher.update_language_data(language_data)

                folder_matcher.reprocess_unmatched_files()

                if mediux:
                  mediux_downloader()

                cover_cleaner(language_data)

                # Clean up empty folders in COVER_DIR
                consolidate_series_folders()
                cleanup_empty_folders(COVER_DIR)

                if force:
                    logging.info("Force flag was set, resetting it to False after first iteration.")
                    force = False

                # Use context manager for UpdateCover
                async with updater:
                    logging.info('Run the UpdateCover process')
                    await updater.run()

                # Explicit cleanup after processing
                gc.collect()
            else:
                logging.info('Found no files or new content on Jellyfin')

                # Calculate and log time until next execution
                if SCHEDULED_TIMES:
                    next_scheduled_time = get_next_scheduled_time()
                    logging.info(format_time_until_next(next_scheduled_time))

                await asyncio.sleep(30)  # Wait for 30 seconds before the next iteration

        except Exception as e:
            logging.error(f"An error occurred in the main loop: {str(e)}")
            logging.error(traceback.format_exc())
            await asyncio.sleep(60)  # Wait for 1 minute before retrying if an error occurs


async def run_application(force: bool):
    webhook_server = WebhookServer()

    if ENABLE_WEBHOOK:
        logger.info("Webhook functionality enabled")
    else:
        logger.info("Webhook functionality disabled")

    await asyncio.gather(
        webhook_server.run_server(),
        main_loop(force, webhook_server)
    )


if __name__ == "__main__":
    setup_logging()

    # Argument parser
    parser = argparse.ArgumentParser(description="Cover cleaner with optional force update.")
    parser.add_argument('--force', action='store_true', help="Force the process to run regardless of conditions.")
    args = parser.parse_args()

    try:
        asyncio.run(run_application(args.force))
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Shutting down.")
    except Exception as e:
        logger.critical(f"Critical error occurred: {str(e)}")
        logger.critical(traceback.format_exc())
