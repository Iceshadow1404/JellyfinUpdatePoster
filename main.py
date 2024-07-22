# src/main.py
import os
import time
import json
import threading
import argparse
from pathlib import Path
from typing import Dict
from src.constants import RAW_COVER_DIR, COVER_DIR, POSTER_DIR, COLLECTIONS_DIR, CONSUMED_DIR, REPLACED_DIR, OUTPUT_FILENAME, PROCESSING_LOG

try:
    from src.CoverCleaner import organize_covers
    from src.getIDs import start_get_and_save_series_and_movie
    from src.updateCover import clean_json_names, assign_images_and_update_jellyfin, missing_folders
    from src.utils import log, ensure_dir
    from src.config import JELLYFIN_URL, API_KEY

except ImportError as e:
    print(f"Error importing modules: {e}")
    exit(1)

# Flag to stop threads
stop_thread = threading.Event()

def setup_directories():
    """Create necessary directories if they don't exist."""
    for dir_path in [POSTER_DIR, COVER_DIR, COLLECTIONS_DIR, CONSUMED_DIR, RAW_COVER_DIR, REPLACED_DIR]:
        ensure_dir(dir_path)

def clean_log_files():
    """Remove old log files and create new ones."""
    log_files = [PROCESSING_LOG, './missing_folders.txt']
    for log_file in log_files:
        if os.path.exists(log_file):
            os.remove(log_file)
        Path(log_file).touch()

def main():
    """Main function for processing covers and updating Jellyfin."""
    try:
        clean_log_files()
        organize_covers()
        start_get_and_save_series_and_movie()
        clean_json_names(OUTPUT_FILENAME)
        missing_folders.clear()
        assign_images_and_update_jellyfin(OUTPUT_FILENAME)

        if missing_folders:
            with open("./missing_folders.txt", 'a', encoding='utf-8') as f:
                for missing in missing_folders:
                    f.write(f"{missing}\n")
        else:
            print("No missing folders to write.")

    except Exception as e:
        print(f"Error in main function: {str(e)}")
        log(f"Error in main function: {str(e)}", success=False)

def check_raw_cover():
    """Check Raw Cover directory every 10 seconds for new files."""
    while not stop_thread.is_set():
        try:
            if any(RAW_COVER_DIR.iterdir()):
                print("Found new Files")
                main()
        except Exception as e:
            error_message = f"Error checking raw cover: {str(e)}"
            print(error_message)
            log(error_message, success=False)
        time.sleep(10)
    print("Checker thread stopped.")

def run_program(run_main_immediately=False):
    """Main program entry point."""
    setup_directories()

    if run_main_immediately:
        main()

    checker_thread = threading.Thread(target=check_raw_cover)
    checker_thread.start()

    try:
        while not stop_thread.is_set():
            start_get_and_save_series_and_movie()
            time.sleep(30)
    except KeyboardInterrupt:
        print("Main program is closing...")
        stop_thread.set()
        checker_thread.join()
        print("Checker thread has been terminated.")

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description="Jellyfin Cover Manager")
        parser.add_argument("--main", action="store_true", help="Run the main function immediately after start")
        args = parser.parse_args()

        run_program(run_main_immediately=args.main)
    except Exception as e:
        print(f"Unhandled exception in main script: {e}")