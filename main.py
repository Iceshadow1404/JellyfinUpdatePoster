# src/main.py
import os
import time
import json
import threading
import argparse
import traceback
from pathlib import Path
from typing import Dict
from src.constants import *
import tempfile
import errno
import asyncio


try:
    from src.CoverCleaner import organize_covers
    from src.getIDs import start_get_and_save_series_and_movie
    from src.updateCover import clean_json_names, assign_images_and_update_jellyfin, missing_folders
    from src.utils import log, ensure_dir
    from src.config import *
    from src.webhook import *
    from src.mediux_downloader import mediux_downloader

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
    log_files = [PROCESSING_LOG, MISSING_FOLDER, MISSING]
    for log_file in log_files:
        if os.path.exists(log_file):
            os.remove(log_file)
        Path(log_file).touch()

def acquire_lock(lock_file):
    try:
        if os.path.exists(lock_file):
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())
                if pid_exists(pid):
                    return None

        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        return lock_file
    except IOError:
        return None


def release_lock(lock_file):
    if lock_file and os.path.exists(lock_file):
        os.remove(lock_file)

def pid_exists(pid):
    """Check whether pid exists in the current process table."""
    if pid < 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno == errno.EPERM
    else:
        return True


async def main():
    """Main function for processing covers and updating Jellyfin."""
    lock_file = os.path.join(tempfile.gettempdir(), 'jellyfin_cover_manager.lock')
    lock = acquire_lock(lock_file)

    if lock is None:
        log("Another instance of the main function is already running. Skipping this execution.", success=False)
        return

    try:
        clean_log_files()
        organize_covers()
        await start_get_and_save_series_and_movie()

        try:
            clean_json_names(OUTPUT_FILENAME)
        except json.JSONDecodeError as json_error:
            log(f"JSON decoding error: {str(json_error)}. Creating new files...", success=False)
            await delete_corrupted_files()
            return

        missing_folders.clear()
        await assign_images_and_update_jellyfin(OUTPUT_FILENAME)

        if missing_folders:
            if os.path.exists(MISSING_FOLDER):
                with open(MISSING_FOLDER, 'a', encoding='utf-8') as f:
                    for missing in missing_folders:
                        f.write(f"{missing}\n")
        else:
            log("No missing folders to write.", success=True)
    except OSError as exc:
        if exc.errno == 36:
            log(f"Filename too long {str(exc)}", success=False)
    except Exception as e:
        log(f"Error in main function: {str(e)}", success=False)
    finally:
        release_lock(lock)

async def delete_corrupted_files():
    """Delete existing files and recreate them with fresh data."""
    files_to_recreate = [RAW_FILENAME, OUTPUT_FILENAME, ID_CACHE_FILENAME]

    try:
        for file in files_to_recreate:
            if os.path.exists(file):
                os.remove(file)
                log(f"Deleted existing file: {file}", success=True)

        await start_get_and_save_series_and_movie()
        clean_json_names(OUTPUT_FILENAME)

        log("Successfully recreated and populated new files", success=True)
    except Exception as e:
        log(f"Error recreating files: {str(e)}", success=False)

async def check_raw_cover():
    """Check Raw Cover directory every 10 seconds for new files."""
    while not stop_thread.is_set():
        try:
            for file in Path(RAW_COVER_DIR).iterdir():
                if file.suffix.lower() in ['.filepart']:
                    while file.exists():
                        print(f"Waiting for {file.name} to finish transferring...")
                        await asyncio.sleep(1)
                    continue

                if file.suffix.lower() in ['.zip', '.png', '.jpg', '.jpeg', '.webp']:
                    initial_size = file.stat().st_size
                    await asyncio.sleep(1)
                    if file.stat().st_size == initial_size:
                        log(f"Found new file: {file.name}")
                        await main()
                        break
            if os.path.getsize(MEDIUX_FILE) != 0:
                log("mediux.txt is not empty. Running mediux_downloader.")
                log("waiting for additional links")
                await asyncio.sleep(10)
                await mediux_downloader()
        except Exception as e:
            error_message = f"Error checking raw cover: {str(e)}"
            log(error_message, success=False)

        await asyncio.sleep(5)

    print("Checker thread stopped.")

async def run_program(run_main_immediately=False):
    """Main program entry point."""
    setup_directories()
    try:
        if os.path.getsize(MEDIUX_FILE) != 0:
            await mediux_downloader()
    except FileNotFoundError:
        if not os.path.exists(MEDIUX_FILE):
            with open(MEDIUX_FILE, 'w') as f:
                pass

    if run_main_immediately:
        await main()

    checker_task = asyncio.create_task(check_raw_cover())

    try:
        while not stop_thread.is_set():
            await start_get_and_save_series_and_movie()
            await asyncio.sleep(30)
    except KeyboardInterrupt:
        print("Main program is closing...")
        stop_thread.set()
        await checker_task
        print("Checker task has been terminated.")

if __name__ == '__main__':
    try:
        clean_log_files()
        parser = argparse.ArgumentParser(description="Jellyfin Cover Manager")
        parser.add_argument("--main", action="store_true", help="Run the main function immediately after start")
        args = parser.parse_args()

        asyncio.run(run_program(run_main_immediately=args.main))
    except Exception as e:
        print(f"Unhandled exception in main script: {e}")
        traceback.print_exc()