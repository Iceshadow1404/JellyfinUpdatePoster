import asyncio
import os
import logging
import argparse
import time
import traceback
import gc

from src.coverCleaner import cover_cleaner, load_language_data
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
from src.file_watcher import CoverMonitor

logger = logging.getLogger(__name__)


async def main_loop(force: bool, webhook_server: WebhookServer):
    updater = UpdateCover()
    cover_monitor = CoverMonitor(COVER_DIR)
    cover_monitor.start()

    try:
        while True:
            try:
                RAW_COVER_DIR.mkdir(parents=True, exist_ok=True)

                mediux = False
                if os.path.exists(MEDIUX_FILE):
                    with open(MEDIUX_FILE, 'r') as file:
                        content = file.read().rstrip()
                        mediux = bool(content)
                else:
                    with open(MEDIUX_FILE, 'w'):
                        pass

                content_changed = check_jellyfin_content()
                webhook_triggered = webhook_server.get_trigger_status() if ENABLE_WEBHOOK else False
                file_changes = cover_monitor.has_changes()

                if file_changes or content_changed or force or mediux or webhook_triggered:
                    if webhook_triggered:
                        logging.info('Process triggered by webhook!')
                    elif file_changes:
                        logging.info('New files detected in monitoring directory!')
                    else:
                        logging.info('Found new Jellyfin content or --force flag set!')

                    get_jellyfin_content()
                    collect_titles()
                    update_output_file()

                    if file_changes or mediux:
                        if mediux:
                            await mediux_downloader()
                        cover_cleaner()
                        mediux = False

                    language_data = load_language_data()
                    folder_matcher = FolderMatcher(language_data)
                    folder_matcher.reprocess_unmatched_files()
                    cleanup_empty_folders()

                    os.system('sync')
                    await asyncio.sleep(2)

                    updater.scan_directories()

                    if force:
                        logging.info("Force flag was set, resetting it to False after first iteration.")
                        force = False

                    async with updater:
                        logging.info('Run the UpdateCover process')
                        await updater.run()

                    gc.collect()

                    # Reset change detection after processing
                    cover_monitor.reset_changes()
                else:
                    logging.info('No changes detected')

                await asyncio.sleep(5)  # Reduced sleep time for more responsive monitoring

            except Exception as e:
                logging.error(f"An error occurred in the main loop: {str(e)}")
                logging.error(traceback.format_exc())
                await asyncio.sleep(60)

    finally:
        cover_monitor.stop()


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