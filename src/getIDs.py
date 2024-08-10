# src/get_ids.py
import json
import sys

import requests
import re
import os
import time
from typing import List, Dict, Set, Tuple, Optional
from requests.exceptions import RequestException

from src.config import JELLYFIN_URL, API_KEY, TMDB_API_KEY, USE_TMDB
from src.utils import log, ensure_dir
from src.updateCover import clean_json_names, assign_images_and_update_jellyfin, missing_folders
from src.constants import RAW_FILENAME, OUTPUT_FILENAME, ID_CACHE_FILENAME, MISSING_FOLDER


def start_get_and_save_series_and_movie():
    media_list = get_and_save_series_and_movies()
    if media_list:
        new_ids, has_processing_tags = process_media_list(media_list)
        old_ids = load_cached_ids()

        if has_processing_tags:
            log("IMDB or TVDB tags detected or unknown years found. Waiting 30 seconds before refreshing...")
            time.sleep(30)
            if os.path.exists(ID_CACHE_FILENAME):
                os.remove(ID_CACHE_FILENAME)
            return start_get_and_save_series_and_movie()  # Restart the process

        if new_ids != old_ids:
            log("Changes in media items detected. Running main function...")
            clean_json_names(RAW_FILENAME)  # Clean the raw file first
            new_sorted_data = sort_series_and_movies(RAW_FILENAME)
            if new_sorted_data:
                save_if_different(OUTPUT_FILENAME, new_sorted_data)
            save_cached_ids(new_ids)
        else:
            log("No changes detected in media items.")
            log("Waiting for new Files in ./RawCover")
    else:
        log("Failed to retrieve series and movies data.", success=False)


def get_and_save_series_and_movies() -> Optional[List[Dict]]:
    headers = {'X-Emby-Token': API_KEY}
    url = f'{JELLYFIN_URL}/Items'
    params = {
        'Recursive': 'true',
        'IncludeItemTypes': 'Series,Season,Movie,BoxSet,Episode',
        'Fields': 'Name,OriginalTitle,Id,ParentId,ParentIndexNumber,Seasons,IndexNumber,ProductionYear',
        'isMissing': 'False'
    }

    attempt = 0
    retry_delay = 5

    while True:
        attempt += 1
        try:
            response = requests.get(url, headers=headers, params=params)

            if response.status_code == 401:
                log("Invalid API Key. Please check your API key and try again.", success=False)
                time.sleep(retry_delay)
                continue

            response.raise_for_status()

            items = response.json().get('Items')
            if not items:
                log("No items found in the response", success=False)
                time.sleep(retry_delay)
                continue

            media_list = [create_media_info(item) for item in items]

            with open(RAW_FILENAME, 'w', encoding='utf-8') as f:
                json.dump(media_list, f, ensure_ascii=False, indent=4)

            return media_list

        except RequestException as e:
            log(f"Request failed (Attempt {attempt}): {e}", success=False)
            log(f"Retrying in {retry_delay} seconds (Attempt {attempt})...")
            time.sleep(retry_delay)

    return None


def create_media_info(item: Dict) -> Dict:
    media_info = {
        'Id': item['Id'],
        'Name': clean_movie_name(item.get('Name', '')),
        'ParentId': item.get('ParentId'),
        'Type': item['Type'],
        'Year': item.get('ProductionYear', 'Unknown'),
    }
    if 'OriginalTitle' in item:
        media_info['OriginalTitle'] = item['OriginalTitle']
    if item.get('Type') == 'Episode':
        media_info['IndexNumber'] = item.get('IndexNumber')

    return media_info


def clean_movie_name(name: str) -> str:
    return re.sub(r' \(\d{4}\)$', '', name)


def process_media_list(media_list: List[Dict]) -> Tuple[Set[str], bool]:
    new_ids = set()
    has_processing_tags = False
    for item in media_list:
        new_ids.add(item['Id'])
        if item['Type'] in ['Series', 'Movie']:
            if 'Name' in item and (
                    re.search(r'\[imdbid-tt\d+\]', item['Name']) or
                    re.search(r'\[tvdbid-\d+\]', item['Name'])):
                has_processing_tags = True
                log(f"Processing tag found in: {item['Name']}")
    return new_ids, has_processing_tags


def load_cached_ids() -> Set[str]:
    if os.path.exists(ID_CACHE_FILENAME):
        with open(ID_CACHE_FILENAME, 'r') as f:
            return set(json.load(f))
    return set()


def save_cached_ids(ids: Set[str]):
    with open(ID_CACHE_FILENAME, 'w', encoding="utf-8") as f:
        json.dump(list(ids), f)


def sort_series_and_movies(input_filename: str) -> Optional[List[Dict]]:
    try:
        with open(input_filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except json.JSONDecodeError as e:
        log(f"Error loading JSON file: {e}", success=False)
        return None

    series_dict = {}
    boxsets = []
    episodes = {}

    for item in data:
        if item['Type'] == 'BoxSet':
            boxsets.append(item)
        elif item['Type'] == 'Season':
            process_season(item, series_dict)
        elif item['Type'] == 'Episode':
            process_episode(item, episodes)
        else:
            process_series_or_movie(item, series_dict)

    result = create_sorted_result(series_dict, boxsets, episodes)
    return result


def process_season(item: Dict, series_dict: Dict):
    parent_id = item['ParentId']
    season_name = item['Name']
    season_id = item['Id']

    if parent_id not in series_dict:
        series_dict[parent_id] = {"Seasons": {}}

    if season_name.startswith("Specials"):
        series_dict[parent_id]["Seasons"]["Season 0"] = {"Id": season_id}
    else:
        try:
            season_number = int(season_name.split(" ")[-1])
            series_dict[parent_id]["Seasons"][f"Season {season_number}"] = {"Id": season_id}
        except ValueError:
            print("Could not find Season")

def process_episode(item: Dict, episodes: Dict):
    parent_id = item['ParentId']
    episode_id = item['Id']
    episode_number = item['IndexNumber']

    if parent_id not in episodes:
        episodes[parent_id] = {}

    episodes[parent_id][f"{episode_number:02d}"] = episode_id

def process_series_or_movie(item: Dict, series_dict: Dict):
    series_id = item['Id']
    series_name = item.get('Name')
    original_title = item.get('OriginalTitle')
    item_type = item.get('Type')

    if series_id not in series_dict:
        series_dict[series_id] = {"Name": series_name, "Type": item_type}
        if item_type != "Movie":
            series_dict[series_id]["Seasons"] = {}
    else:
        series_dict[series_id]["Name"] = series_name
        series_dict[series_id]["Type"] = item_type

    if original_title:
        series_dict[series_id]["OriginalTitle"] = original_title

    if 'Year' in item:
        series_dict[series_id]["Year"] = item['Year']

def create_sorted_result(series_dict: Dict, boxsets: List[Dict], episodes: Dict) -> List[Dict]:
    result = []

    for series_id, details in series_dict.items():
        if "Name" in details:
            series_info = create_series_info(series_id, details, episodes)
            result.append(series_info)

    result.sort(key=lambda x: x['Name'])

    for boxset in boxsets:
        boxset_info = create_boxset_info(boxset)
        result.append(boxset_info)

    return result

def create_series_info(series_id: str, details: Dict, episodes: Dict) -> Dict:
    series_info = {
        "Id": series_id,
        "Name": details["Name"]
    }
    if "OriginalTitle" in details:
        series_info["OriginalTitle"] = details["OriginalTitle"]
    if "Year" in details:
        series_info["Year"] = details["Year"]

    if details.get("Type") == "Movie":
        # For movies, we don't include the Seasons field
        return series_info

    # For TV series, include the Seasons field
    series_info["Seasons"] = {}
    for season_name, season_data in details["Seasons"].items():
        season_id = season_data["Id"]
        series_info["Seasons"][season_name] = {
            "Id": season_id
        }
        if season_id in episodes and episodes[season_id]:
            series_info["Seasons"][season_name]["Episodes"] = episodes[season_id]

    if details["Name"].upper() != details.get("OriginalTitle", "").upper():
        series_info["EnglishTitle"] = details.get("OriginalTitle", details["Name"])

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

    if old_data != new_data:
        log("Changes detected, saving the new file.")
        try:
            with open(filename, 'w', encoding='utf-8') as outfile:
                json.dump(new_data, outfile, ensure_ascii=False, indent=4)
            log(f"Successfully saved new data to {filename}")
        except IOError as e:
            log(f"Error saving JSON file: {e}", success=False)

        if os.path.exists(MISSING_FOLDER):
            os.remove(MISSING_FOLDER)

        try:
            assign_images_and_update_jellyfin(filename)
        except OSError as exc:
            if exc.errno == 36:
                log(f"Filename too long {str(exc)}", success=False)
        if missing_folders:
            with open(MISSING_FOLDER, 'a', encoding='utf-8') as f:
                for missing in missing_folders:
                    f.write(missing + "\n")
    else:
        log("No changes detected in the data.")


if __name__ == "__main__":
    get_and_save_series_and_movies()