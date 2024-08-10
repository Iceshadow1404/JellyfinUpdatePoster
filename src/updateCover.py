# src/update_cover.py
import os
import json
import time
import requests
import subprocess
from base64 import b64encode
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from difflib import SequenceMatcher

from src.config import *
from src.utils import log, get_content_type
from src.constants import COVER_DIR, POSTER_DIR, COLLECTIONS_DIR, OUTPUT_FILENAME, MISSING
from src.webhook import webhook

missing_folders: List[str] = []
used_folders: List[Path] = []


def get_english_title(title, year, media_type='movie'):
    url = f"https://api.themoviedb.org/3/search/{media_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "year": year,
        "language": "en-US"
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        results = response.json().get("results", [])
        if results:
            # Sort results by popularity (assuming more popular results are more likely to be correct)
            sorted_results = sorted(results, key=lambda x: x.get('popularity', 0), reverse=True)

            for result in sorted_results[:3]:  # Check top 3 results
                result_title = result['title'] if media_type == 'movie' else result['name']
                result_year = result['release_date'][:4] if media_type == 'movie' else result['first_air_date'][:4]

                # Check if the result is in English and matches the year
                if result_year == str(year) and all(ord(c) < 128 for c in result_title):
                    return result_title

    return None  # Return None if no suitable English title is found

def clean_json_names(json_filename: str):
    json_path = Path(json_filename)

    with json_path.open('r', encoding='utf-8') as f:
        json_data = json.load(f)

    for series in json_data:
        if 'Name' in series:
            series['Name'] = clean_name(series['Name'])
        if 'OriginalTitle' in series:
            series['OriginalTitle'] = clean_name(series['OriginalTitle'])
        if 'EnglishTitle' in series:
            series['EnglishTitle'] = clean_name(series['EnglishTitle'])

    with json_path.open('w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=4)

def clean_name(name: str) -> str:
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '&', "'", '!', '?', '[', ']', '!']
    for char in invalid_chars:
        name = name.replace(char, '')
    return name

def assign_images_and_update_jellyfin(json_filename: str):
    json_path = Path(json_filename)

    if not json_path.exists():
        log(f"The JSON file {json_filename} could not be found.", success=False)
        return

    with json_path.open('r', encoding='utf-8') as f:
        json_data = json.load(f)

    for item in json_data:
        process_item(item)

    with json_path.open('w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=4)

    log("Updated all posters and added English titles where applicable")
    if USE_HA:
        webhook(HA_WEBHOOK_URL, HA_WEBHOOK_ID)

    save_missing_folders()


def process_item(item: Dict):
    clean_json_names(OUTPUT_FILENAME)
    # Check if EnglishTitle is missing or invalid
    if 'EnglishTitle' not in item or not all(ord(c) < 128 for c in item['EnglishTitle']):
        if USE_TMDB:
            media_type = 'tv' if 'Seasons' in item else 'movie'
            english_title = get_english_title(item.get('OriginalTitle', item.get('Name')), item.get('Year'), media_type)
            if english_title:
                item['EnglishTitle'] = english_title
                # Save the updated item immediately
                update_sorted_series_item(item)
        else:
            log(f"TMDB lookup disabled. Skipping English title retrieval for {item.get('Name')}", success=False)

    # Process posters and seasons
    item_dir = get_item_directory(item)
    if not item_dir:
        return item

    main_poster_path = find_main_poster(item_dir)
    if main_poster_path:
        update_jellyfin(item['Id'], main_poster_path, f"{clean_name(item.get('Name'))} ({item.get('Year')})", 'Primary')
    else:
        log(f"Main Cover not Found for item: {clean_name(item.get('Name'))} ({item.get('Year')})", success=False)
        missing_folders.append(f"Main Cover not Found: {item_dir / 'poster'}")

    backdrop_path = find_backdrop(item_dir)
    if backdrop_path:
        update_jellyfin(item['Id'], backdrop_path, f"{clean_name(item.get('Name'))} ({item.get('Year')})", 'Backdrop')
    else:
        log(f"Backdrop not Found for item: {clean_name(item.get('Name'))} ({item.get('Year')})", success=False)


    if 'Seasons' in item:
        process_seasons(item, item_dir)

    return item

def update_sorted_series_item(updated_item):
    sorted_series_path = Path(OUTPUT_FILENAME)
    if not sorted_series_path.exists():
        log(f"The file {OUTPUT_FILENAME} could not be found.", success=False)
        return

    with sorted_series_path.open('r', encoding='utf-8') as f:
        sorted_series = json.load(f)

    for i, item in enumerate(sorted_series):
        if item['Id'] == updated_item['Id']:
            sorted_series[i] = updated_item
            break

    with sorted_series_path.open('w', encoding='utf-8') as f:
        json.dump(sorted_series, f, indent=4, ensure_ascii=False)


def get_item_directory(item: Dict) -> Optional[Path]:
    item_type = item.get('Type', 'Series' if 'Seasons' in item else 'Movie')
    item_name = clean_name(item.get('Name', '').strip())
    item_original_title = clean_name(item.get('OriginalTitle', item_name).strip())
    item_year = item.get('Year')
    english_title = clean_name(item.get('EnglishTitle', ''))

    if item_type == "BoxSet":
        possible_dirs = [
            COLLECTIONS_DIR / item_name,
            COLLECTIONS_DIR / item_original_title
        ]
        if english_title:
            possible_dirs.insert(0, COLLECTIONS_DIR / english_title)
    else:
        possible_dirs = [
            POSTER_DIR / f"{item_original_title} ({item_year})",
            POSTER_DIR / f"{item_name} ({item_year})"
        ]
        if english_title:
            possible_dirs.insert(0, POSTER_DIR / f"{english_title} ({item_year})")

    for dir in possible_dirs:
        if dir.exists():
            used_folders.append(dir)
            return dir

    # If we reach here, no directory was found
    base_dir = COLLECTIONS_DIR if item_type == "BoxSet" else POSTER_DIR
    if item_type == "BoxSet":
        missing_name = english_title or item_name
        missing_folder = f"Folder not found: {base_dir / missing_name}"
    else:
        missing_name = english_title or item_original_title
        missing_folder = f"Folder not found: {base_dir / f'{missing_name} ({item_year})'}"

    log(missing_folder, success=False)
    missing_folders.append(missing_folder)
    return None

def find_main_poster(item_dir: Path) -> Path:
    for poster_filename in ['poster.png', 'poster.jpeg', 'poster.jpg', 'poster.webp']:
        poster_path = item_dir / poster_filename
        if poster_path.exists():
            return poster_path
    return None

def process_seasons(item: Dict, item_dir: Path):
    for season_name, season_data in item.get('Seasons', {}).items():
        if 'Id' in season_data:
            season_number = season_name.split(" ")[-1]
            season_image_filename = f'Season{season_number.zfill(2)}'
            season_image_path = find_season_image(item_dir, season_image_filename)

            if season_image_path:
                update_jellyfin(season_data['Id'], season_image_path, f"{clean_name(item.get('Name'))} ({item.get('Year')}) - {season_name}", 'Primary')
            else:
                log(f"Season image not found for item - {clean_name(item.get('Name'))} ({item.get('Year')}) - {season_name}", success=False)
                missing_folders.append(f"Season Cover not Found: {item_dir / season_image_filename}")

            # Process episodes
            process_episodes(item, season_data, item_dir, season_number)

def process_episodes(item: Dict, season_data: Dict, item_dir: Path, season_number: str):
    for episode_number, episode_id in season_data.get('Episodes', {}).items():
        if not episode_id:
            log(f"Skipping episode due to missing Id: S{season_number}E{episode_number} in {item.get('Name', 'Unknown Series')}", success=False)
            continue

        try:
            int(episode_number)  # This will raise ValueError if episode_number is not a valid integer
        except ValueError:
            log(f"Skipping episode due to invalid episode number: S{season_number}E{episode_number} in {item.get('Name', 'Unknown Series')}", success=False)
            continue

        episode_image_filename = f'S{season_number.zfill(2)}E{episode_number.zfill(2)}'
        episode_image_path = find_episode_image(item_dir, episode_image_filename)

        if episode_image_path:
            try:
                update_jellyfin(episode_id, episode_image_path, f"{clean_name(item.get('Name', 'Unknown'))} ({item.get('Year', 'Unknown')}) - S{season_number}E{episode_number}", 'Primary')
            except Exception as e:
                log(f"Error updating image for episode S{season_number}E{episode_number} in {item.get('Name', 'Unknown Series')}: {str(e)}", success=False)

def find_backdrop(item_dir: Path) -> Optional[Path]:
    for ext in ['png', 'jpg', 'jpeg', 'webp']:
        backdrop_path = item_dir / f"backdrop.{ext}"
        if backdrop_path.exists():
            return backdrop_path
    return None


def find_episode_image(item_dir: Path, episode_image_filename: str) -> Optional[Path]:
    for ext in ['png', 'jpg', 'jpeg', 'webp']:
        episode_image_path = item_dir / f"{episode_image_filename}.{ext}"
        if episode_image_path.exists():
            return episode_image_path
    return None

def save_missing_folders():
    all_folders = set(POSTER_DIR.glob('*')) | set(COLLECTIONS_DIR.glob('*'))
    unused_folders = all_folders - set(used_folders)

    with open(MISSING, 'w', encoding='utf-8') as f:
        for folder in unused_folders:
            f.write(f"Didn't use Folder: {folder}\n")
    log(f"Saved extra / unnecessary Folders to {MISSING}")

def find_season_image(item_dir: Path, season_image_filename: str) -> Path:
    for ext in ['png', 'jpg', 'jpeg', 'webp']:
        season_image_path = item_dir / f"{season_image_filename}.{ext}"
        if season_image_path.exists():
            return season_image_path
    return None

def update_jellyfin(id: str, image_path: Path, item_name: str, image_type: str = 'Primary'):
    endpoint = f'/Items/{id}/Images/{image_type}/0'
    url = f"{JELLYFIN_URL}{endpoint}"
    headers = {
        'X-Emby-Token': API_KEY,
        'Content-Type': get_content_type(str(image_path))
    }

    if not image_path.exists():
        log(f"Image file not found: {image_path}. Skipping.", success=False)
        return

    with image_path.open('rb') as file:
        image_data = file.read()
        image_base64 = b64encode(image_data)

    try:
        response = requests.post(url, headers=headers, data=image_base64)
        response.raise_for_status()
        log(f'Updated {image_type} image for {clean_name(item_name)} successfully.')
    except requests.RequestException as e:
        status_code = e.response.status_code if e.response else "N/A"
        response_text = e.response.text if e.response else "N/A"
        log(f'Error updating {image_type} image for {clean_name(item_name)}. Status Code: {status_code}', success=False)
        log(f'Response: {response_text}', success=False)

if __name__ == "__main__":
    # This block can be used for testing the module independently
    json_filename = 'sorted_series.json'
    clean_json_names(json_filename)
    assign_images_and_update_jellyfin(json_filename)