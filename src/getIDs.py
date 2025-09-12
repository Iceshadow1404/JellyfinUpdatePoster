import requests
import json
import os
import logging
import re
import time
from typing import List, Dict, Optional
from collections import OrderedDict

from src.constants import OUTPUT_FILENAME, BLACKLIST_FILENAME
from src.config import JELLYFIN_URL, API_KEY, INCLUDE_EPISODES
from src.blacklist import load_blacklist, save_blacklist, add_to_blacklist, update_output_file
from src.coverCleaner import sanitize_folder_name

logger = logging.getLogger(__name__)


def clean_name(name: str) -> str:
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '&', "'", '!', '?', '[', ']', '!', '&']
    for char in invalid_chars:
        name = name.replace(char, '')
    return name

def clean_movie_name(name: str) -> str:
    # Remove year in parentheses at the end
    name = re.sub(r' \(\d{4}\)$', '', name)
    # Remove any remaining parentheses and their contents
    name = re.sub(r'\([^)]*\)', '', name)
    # Remove any square brackets and their contents
    name = re.sub(r'\[[^]]*\]', '', name)
    # Trim any leading or trailing whitespace
    return name.strip()

def extract_folder_from_path(path: str, media_type: str) -> str:
    if not path:
        return ""

    parts = path.strip('/').split('/')

    if media_type.lower() == 'movie':
        # Movie file's parent directory
        if len(parts) >= 2:
            return parts[-2]  # second last segment
        else:
            return parts[-1]  # fallback last segment
    elif media_type.lower() == 'series':
        return parts[-1]
    else:
        return parts[-1]

def get_series_and_movies() -> Optional[List[Dict]]:
    headers = {'X-Emby-Token': API_KEY}
    url = f'{JELLYFIN_URL}/Items'

    item_types = ['Series', 'Season', 'Movie', 'BoxSet']

    if INCLUDE_EPISODES:
        item_types.append('Episode')

    params = {
        'Recursive': 'true',
        'IncludeItemTypes': ','.join(item_types),
        'Fields': 'Name,OriginalTitle,Id,ParentId,ParentIndexNumber,IndexNumber,ProductionYear,ProviderIds,Path',
        'isMissing': 'False'
    }

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            items = response.json()['Items']

            # Filter out blacklisted items
            items = [item for item in items if item['Id']]

            # Check for processing tags
            items_with_tags = [item for item in items if item['Type'] in ['Series', 'Movie'] and
                               ('Name' in item and (re.search(r'\[imdbid-tt\d+\]', item['Name']) or
                                                    re.search(r'\[tvdbid-\d+\]', item['Name'])))]

            if items_with_tags:
                if attempt == max_retries - 1:
                    logger.info(f"Processing tags still present after {max_retries} attempts. Adding items to blacklist.")
                    for item in items_with_tags:
                        add_to_blacklist(item['Id'])
                        items.remove(item)
                else:
                    logger.info(f"Processing tags found in {len(items_with_tags)} items. Waiting 5 seconds before retry...")
                    for item in items_with_tags:
                        logger.info(f"Item with processing tag: {item['Name']} (ID: {item['Id']})")
                    time.sleep(20)
                    continue  # Retry the request

            return items
        except requests.RequestException as e:
            logger.error(f"Error fetching data from Jellyfin API (Attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)  # Wait before retrying
            else:
                logger.error("Max retries reached. Unable to fetch data.")
                return None

def process_items(items: List[Dict]) -> List[Dict]:
    processed_items = []
    series_dict = {}
    boxsets = []

    for item in items:
        # Skip virtual items
        if item.get('LocationType') == 'Virtual':
            logger.debug(f"Skipping virtual item: {item.get('Name', 'Unknown')} (ID: {item.get('Id', 'Unknown')})")
            continue
        if item['Type'] != 'BoxSet':
            item['Name'] = clean_name(clean_movie_name(item['Name']))
            if 'OriginalTitle' in item:
                item['OriginalTitle'] = clean_name(clean_movie_name(item['OriginalTitle']))
        else:
            # For BoxSets, only clean invalid characters, but keep content in parentheses
            item['Name'] = clean_name(item['Name'])
            if 'OriginalTitle' in item:
                item['OriginalTitle'] = clean_name(item['OriginalTitle'])

        tmdb_id = item.get('ProviderIds', {}).get('Tmdb')

        if item["Type"] == "Series":
            processed_item = {
                "Id": item["Id"],
                "Name": item["Name"],
                "Type": "Series",
                "LibraryId": item.get("ParentId", ""),
                "OriginalTitle": item.get("OriginalTitle", item["Name"]),
                "Year": item.get("ProductionYear"),
                "TMDb": item.get("ProviderIds", {}).get("Tmdb"),
                "Path": extract_folder_from_path(item.get("Path", ""), "Series"),
                "Seasons": OrderedDict(),
            }
            series_dict[item["Id"]] = processed_item
        elif item['Type'] == 'Season':
            series_id = item['SeriesId']
            if series_id in series_dict:
                season_number = item.get('IndexNumber', 0)
                season_name = f"Season {season_number}"
                series_dict[series_id]['Seasons'][season_name] = {
                    "Id": item['Id'],
                    "Episodes": OrderedDict()
                }
        elif item['Type'] == 'Episode':
            series_id = item['SeriesId']
            season_index = item.get('ParentIndexNumber', 0)
            if series_id in series_dict:
                season_name = f"Season {season_index}"
                if season_name in series_dict[series_id]['Seasons']:
                    episode_number = item.get('IndexNumber', 0)
                    episode_key = f"{episode_number:02d}"  # Episode number with leading zeros
                    series_dict[series_id]['Seasons'][season_name]['Episodes'][episode_key] = item['Id']
        elif item["Type"] == "Movie":
            processed_item = {
                "Id": item["Id"],
                "Name": item["Name"],
                "Type": "Movie",
                "LibraryId": item.get("ParentId", ""),
                "OriginalTitle": item.get("OriginalTitle", item["Name"]),
                "Year": item.get("ProductionYear"),
                "TMDb": item.get("ProviderIds", {}).get("Tmdb"),
                "Path": extract_folder_from_path(item.get("Path", ""), "Movie"),
            }
            processed_items.append(processed_item)
        elif item["Type"] == "BoxSet":
            processed_item = {
                "Id": item["Id"],
                "Name": item["Name"],
                "Type": "BoxSet",
                "LibraryId": item.get("ParentId", ""),
                "Year": item.get("ProductionYear"),
                "TMDb": item.get("ProviderIds", {}).get("Tmdb"),
                "Path": sanitize_folder_name(item["Name"]),
            }
            boxsets.append(processed_item)

    # Sort seasons and episodes
    for series in series_dict.values():
        series['Seasons'] = OrderedDict(sorted(series['Seasons'].items(), key=lambda x: int(x[0].split()[1])))
        for season in series['Seasons'].values():
            season['Episodes'] = OrderedDict(sorted(season['Episodes'].items(), key=lambda x: int(x[0])))

    processed_items.extend(series_dict.values())
    processed_items.extend(boxsets)
    return processed_items

def get_jellyfin_content(silent=False):
    if not silent:
        logger.info("Starting Jellyfin content retrieval")

    items = get_series_and_movies()
    if silent:
        return items

    if items:
        processed_items = process_items(items)
        processed_items.sort(key=lambda x: x['Name'].lower())

        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(processed_items, f, ensure_ascii=False, indent=4)
        return processed_items
    else:
        if not silent:
            logger.warning("No data to process.")
        return None


if __name__ == "__main__":
    get_jellyfin_content()