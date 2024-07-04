# src/get_ids.py
import json
import requests
import re
import os
from typing import List, Dict, Optional

from src.config import JELLYFIN_URL, API_KEY
from src.utils import log, ensure_dir
from updateCover import clean_json_names, assign_images_and_update_jellyfin, missing_folders

OUTPUT_FILENAME = 'sorted_series.json'
RAW_FILENAME = 'raw.json'


def start_get_and_save_series_and_movie():
    media_list = get_and_save_series_and_movies()
    if media_list:
        new_sorted_data = sort_series_and_movies(RAW_FILENAME)
        if new_sorted_data:
            save_if_different(OUTPUT_FILENAME, new_sorted_data)
        else:
            log("Failed to sort series and movies data.", success=False)
    else:
        log("Failed to retrieve series and movies data.", success=False)


def get_and_save_series_and_movies() -> Optional[List[Dict]]:
    headers = {'X-Emby-Token': API_KEY}
    url = f'{JELLYFIN_URL}/Items'
    params = {
        'Recursive': 'true',
        'IncludeItemTypes': 'Series,Season,Movie,BoxSet',
        'excludeLocationTypes': 'Virtual, Remote, Offline',
        'Fields': 'Name,OriginalTitle,Id,ParentId,ParentIndexNumber,Seasons,ProductionYear',
        'isMissing': 'False'
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
    except requests.RequestException as e:
        log(f"Request failed: {e}", success=False)
        return None

    items = response.json().get('Items')
    if not items:
        log("No items found in the response", success=False)
        return None

    media_list = [create_media_info(item) for item in items]

    with open(RAW_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(media_list, f, ensure_ascii=False, indent=4)

    return media_list


def create_media_info(item: Dict) -> Dict:
    media_info = {
        'Id': item['Id'],
        'Name': clean_movie_name(item.get('Name', '')),
        'ParentId': item.get('ParentId'),
        'Type': item['Type'],
        'Year': item.get('ProductionYear', 'Unknown')
    }
    if 'OriginalTitle' in item:
        media_info['OriginalTitle'] = item['OriginalTitle']
    return media_info


def clean_movie_name(name: str) -> str:
    return re.sub(r' \(\d{4}\)$', '', name)


def sort_series_and_movies(input_filename: str) -> Optional[List[Dict]]:
    try:
        with open(input_filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except json.JSONDecodeError as e:
        log(f"Error loading JSON file: {e}", success=False)
        return None

    series_dict = {}
    boxsets = []

    for item in data:
        if item['Type'] == 'BoxSet':
            boxsets.append(item)
        elif item['Type'] == 'Season':
            process_season(item, series_dict)
        else:
            process_series_or_movie(item, series_dict)

    result = create_sorted_result(series_dict, boxsets)
    return result


def process_season(item: Dict, series_dict: Dict):
    parent_id = item['ParentId']
    season_name = item['Name']
    season_id = item['Id']

    if parent_id not in series_dict:
        series_dict[parent_id] = {}

    if season_name == "Specials":
        series_dict[parent_id]["Season 0"] = season_id
    elif season_name.startswith("Season") or season_name.startswith("Partie"):
        series_dict[parent_id][season_name] = season_id


def process_series_or_movie(item: Dict, series_dict: Dict):
    series_id = item['Id']
    series_name = item.get('Name')
    original_title = item.get('OriginalTitle')

    if series_id not in series_dict:
        series_dict[series_id] = {"Name": series_name}
    else:
        series_dict[series_id]["Name"] = series_name

    if original_title:
        series_dict[series_id]["OriginalTitle"] = original_title

    if 'Year' in item:
        series_dict[series_id]["Year"] = item['Year']


def create_sorted_result(series_dict: Dict, boxsets: List[Dict]) -> List[Dict]:
    result = []

    for series_id, details in series_dict.items():
        if "Name" in details:
            series_info = create_series_info(series_id, details)
            result.append(series_info)

    result.sort(key=lambda x: x['Name'])

    for boxset in boxsets:
        boxset_info = create_boxset_info(boxset)
        result.append(boxset_info)

    return result


def create_series_info(series_id: str, details: Dict) -> Dict:
    series_info = {
        "Id": series_id,
        "Name": details["Name"]
    }
    if "OriginalTitle" in details:
        series_info["OriginalTitle"] = details["OriginalTitle"]
    if "Year" in details:
        series_info["Year"] = details["Year"]

    seasons = {season_name: season_id for season_name, season_id in details.items()
               if season_name not in ["Name", "OriginalTitle", "Year"]}
    if seasons:
        series_info.update(seasons)

    return series_info


def create_boxset_info(boxset: Dict) -> Dict:
    boxset_info = {
        "Id": boxset['Id'],
        "Name": boxset['Name'].replace(" Filmreihe", "").replace(" Collection", ""),
        "Type": "BoxSet"
    }
    if "OriginalTitle" in boxset:
        boxset_info["OriginalTitle"] = boxset["OriginalTitle"]
    if "Year" in boxset:
        boxset_info["Year"] = boxset["Year"]
    return boxset_info


def save_if_different(filename: str, new_data: List[Dict]):
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as file:
                old_data = json.load(file)
        else:
            old_data = None
    except json.JSONDecodeError as e:
        log(f"Error loading old JSON file: {e}", success=False)
        old_data = None

    if old_data is not None and len(old_data) == len(new_data):
        log("No changes detected, not saving the file.")
        log("Waiting for new Files in ./RawCover")
    else:
        log("Changes detected, saving the new file.")

        missing_folders.clear()
        clean_json_names(OUTPUT_FILENAME)
        assign_images_and_update_jellyfin(OUTPUT_FILENAME)

        if os.path.exists('./missing_folders.txt'):
            os.remove('./missing_folders.txt')

        if missing_folders:
            with open("./missing_folders.txt", 'a', encoding='utf-8') as f:
                for missing in missing_folders:
                    f.write(missing + "\n")

    try:
        with open(filename, 'w', encoding='utf-8') as outfile:
            json.dump(new_data, outfile, ensure_ascii=False, indent=4)
    except IOError as e:
        log(f"Error saving JSON file: {e}", success=False)


if __name__ == "__main__":
    start_get_and_save_series_and_movie()