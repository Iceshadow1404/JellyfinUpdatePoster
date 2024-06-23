import os
import time
from threading import Thread
import json

# Import functions from other modules
from CoverCleaner import organize_covers
from getIDs import start_get_and_save_series_and_movie
from updateCover import clean_json_names, assign_images_and_update_jellyfin, missing_folders

with open("config.json", 'r') as file:
    data = json.load(file)

jellyfin_url = data["jellyfin_url"]
api_key = data["api_key"]

json_filename = 'sorted_series.json'

# Directory for Raw Covers
rawCover = "./RawCover"

# Main function for processing
def main():
    try:
        # Remove old log files if they exist
        if os.path.exists('./processing.log'):
            os.remove('./processing.log')

        if os.path.exists('./missing_folders.txt'):
            os.remove('./missing_folders.txt')

        # Create new log files
        with open('./processing.log', 'w') as f:
            pass

        organize_covers()
        start_get_and_save_series_and_movie(api_key, jellyfin_url)
        clean_json_names(json_filename)
        assign_images_and_update_jellyfin(json_filename, jellyfin_url, api_key)

        # Save missing folders to a text file
        with open("./missing_folders.txt", 'a', encoding='utf-8') as f:
            for missing in missing_folders:
                f.write(missing + "\n")

    except Exception as e:
        print(f"Error in main function: {str(e)}")

# Function to check Raw Cover directory every 10 seconds
def check_raw_cover():
    while True:
        try:
            if os.listdir(rawCover):
                main()
        except Exception as e:
            print(f"Error checking raw cover: {str(e)}")
        time.sleep(10)  # Wait for 10 seconds

# Main program entry point
if __name__ == '__main__':
    # Start a thread to continuously check the Raw Cover directory
    checker_thread = Thread(target=check_raw_cover)
    checker_thread.start()
