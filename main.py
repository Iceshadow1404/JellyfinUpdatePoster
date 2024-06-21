from CoverCleaner import organize_covers
from getIDs import start_get_and_save_series_and_movie
from updateCover import clean_json_names, assign_images_and_update_jellyfin, missing_folders
import json
import os

if os.path.exists('processing.log'):
    os.remove('processing.log')

with open('processing.log', 'w') as f:
    pass

with open("config.json", 'r') as file:
    data = json.load(file)

jellyfin_url = data["jellyfin_url"]
api_key = data["api_key"]

json_filename = 'sorted_series.json'

organize_covers()
start_get_and_save_series_and_movie(api_key, jellyfin_url)
clean_json_names(json_filename)
assign_images_and_update_jellyfin(json_filename)

with open("missing_folders.txt", 'a', encoding='utf-8') as f:
    for missing in missing_folders:
        f.write(missing + "\n")