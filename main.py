import os
import time
import json
import threading

# Import functions from other modules
from CoverCleaner import organize_covers, log
from getIDs import start_get_and_save_series_and_movie
from updateCover import clean_json_names, assign_images_and_update_jellyfin, missing_folders

# Load configuration from JSON file
with open("config.json", 'r') as file:
    data = json.load(file)

jellyfin_url = data["jellyfin_url"]
api_key = data["api_key"]

json_filename = 'sorted_series.json'

raw_cover_dir = './RawCover'
cover_dir = './Cover'
movies_dir = os.path.join(cover_dir, 'Poster')
shows_dir = os.path.join(cover_dir, 'Poster')
collections_dir = os.path.join(cover_dir, 'Collections')
consumed_dir = './Consumed'
replaced_dir = './Replaced'

for dir_path in [movies_dir, shows_dir, collections_dir, consumed_dir, raw_cover_dir, replaced_dir]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        log(f"Created directory: {dir_path}")

# Flag to stop threads
stop_thread = threading.Event()

# Main function for processing
def main():
    try:
        # Remove old log files if they exist
        if os.path.exists('./processing.log'):
            os.remove('./processing.log')

        if os.path.exists('./missing_folders.txt'):
            os.remove('./missing_folders.txt')

        # Create new log files
        with open('./processing.log', 'w'):
            pass

        organize_covers()
        start_get_and_save_series_and_movie(api_key, jellyfin_url)
        clean_json_names(json_filename)
        missing_folders.clear()
        assign_images_and_update_jellyfin(json_filename, jellyfin_url, api_key)

        # Check if missing_folders has any entries
        if missing_folders:
            print("Writing missing folders to file...")
            with open("./missing_folders.txt", 'a', encoding='utf-8') as f:
                for missing in missing_folders:
                    f.write(missing + "\n")
        else:
            print("No missing folders to write.")

    except Exception as e:
        print(f"Error in main function: {str(e)}")


# Function to check Raw Cover directory every 10 seconds
def check_raw_cover():
    while not stop_thread.is_set():
        try:
            if os.listdir(raw_cover_dir):
                print("Found new Files")
                main()
        except Exception as e:
            print(f"Error checking raw cover: {str(e)}")
        time.sleep(10)
    print("Checker thread stopped.")


# Main program entry point
if __name__ == '__main__':
    checker_thread = threading.Thread(target=check_raw_cover)
    checker_thread.start()

    try:
        while not stop_thread.is_set():
            start_get_and_save_series_and_movie(api_key, jellyfin_url)
            time.sleep(30)
    except KeyboardInterrupt:
        print("Main program is closing...")
        stop_thread.set()
        checker_thread.join()
        print("Checker thread has been terminated.")