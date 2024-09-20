# src/update_cover.py
import json

import requests
import concurrent.futures
from base64 import b64encode
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from difflib import SequenceMatcher
import threading

from sympy.physics.units import electronvolt

from src.config import *
from src.utils import log, get_content_type
from src.constants import POSTER_DIR, COLLECTIONS_DIR, OUTPUT_FILENAME, MISSING, EXTRA_FOLDER

missing_folders: List[str] = []
extra_folder: List[str] = []

# Global lock for file access
file_lock = threading.Lock()


class DirectoryManager:
    def __init__(self):
        self.directory_lookup: Dict[str, Path] = {}
        self.used_folders: List[Path] = []
        self.scan_directories()

    def scan_directories(self):
        """Scan all directories once and create a lookup dictionary."""
        self.directory_lookup.clear()  # Clear the old data
        for base_dir in [POSTER_DIR, COLLECTIONS_DIR]:
            for item_dir in base_dir.glob('*'):
                if item_dir.is_dir():
                    key = item_dir.name.lower()
                    self.directory_lookup[key] = item_dir

    def get_item_directory(self, item: Dict) -> Optional[Path]:
        global missing_folders
        item_type = item.get('Type', 'Series' if 'Seasons' in item else 'Movie')
        item_name = clean_name(item.get('Name', '').strip())
        item_original_title = clean_name(item.get('OriginalTitle', item_name).strip())
        item_year = item.get('Year')
        english_title = clean_name(item.get('EnglishTitle', ''))

        possible_keys = []
        if item_type == "BoxSet":
            possible_keys = [
                english_title.lower(),
                item_name.lower(),
                item_original_title.lower()
            ]
        else:
            possible_keys = [
                f"{english_title} ({item_year})".lower(),
                f"{item_original_title} ({item_year})".lower(),
                f"{item_name} ({item_year})".lower()
            ]

        for key in possible_keys:
            if key in self.directory_lookup:
                self.used_folders.append(self.directory_lookup[key])
                return self.directory_lookup[key]

        # If we reach here, no directory was found
        base_dir = COLLECTIONS_DIR if item_type == "BoxSet" else POSTER_DIR
        if item_type == "BoxSet":
            missing_name = english_title or item_name
            missing_folder = f"Folder not found: {base_dir / missing_name}"
        else:
            missing_name = english_title or item_original_title
            if english_title:
                missing_folder = f"Folder not found: {base_dir / f'{english_title} ({item_year})'}"
            else:
                missing_folder = f"Folder not found: {base_dir / f'{missing_name} ({item_year})'}"



        missing_folders.append(missing_folder)
        log(missing_folder, success=False)
        return None

def save_missing_folders():
    global missing_folders
    all_folders = set(POSTER_DIR.glob('*')) | set(COLLECTIONS_DIR.glob('*'))
    unused_folders = all_folders - set(directory_manager.used_folders)

    with open(MISSING, 'w', encoding='utf-8') as f:
        for folder in missing_folders:
            f.write(f"{folder}\n")

    log(f"Saved missing and unused folders to {MISSING} and {EXTRA_FOLDER}")

    with open(EXTRA_FOLDER, 'w', encoding='utf-8') as f:
        for folder in unused_folders:
            f.write(f"Didn't use Folder: {folder}\n")

# Initialize the DirectoryManager at the module level
directory_manager = DirectoryManager()


def get_english_title(title, year, original_title=None, media_type='movie'):
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

            best_match = None
            highest_similarity = 0

            for result in sorted_results[:5]:  # Check top 5 results
                result_title = result['title'] if media_type == 'movie' else result['name']
                result_year = result['release_date'][:4] if media_type == 'movie' else result['first_air_date'][:4]
                result_original_title = result.get('original_title', result_title)

                # Check if the result is in English and the year matches
                if result_year == str(year) and all(ord(c) < 128 for c in result_title):
                    # Calculate similarity with the search title
                    title_similarity = SequenceMatcher(None, title.lower(), result_title.lower()).ratio()

                    # If we have an original title, calculate similarity with it as well
                    if original_title:
                        original_title_similarity = SequenceMatcher(None, original_title.lower(),
                                                                    result_original_title.lower()).ratio()
                        similarity = max(title_similarity, original_title_similarity)
                    else:
                        similarity = title_similarity

                    if similarity > highest_similarity:
                        highest_similarity = similarity
                        best_match = result_title

            if best_match and highest_similarity > 0.3:
                return best_match

    return None  # Return None if no suitable English title is found

def clean_json_names(json_filename: str):
    json_path = Path(json_filename)

    with file_lock:
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
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '&', "'", '!', '?', '[', ']', '!', '&']
    for char in invalid_chars:
        name = name.replace(char, '')
    return name

def assign_images_and_update_jellyfin(json_filename: str):
    json_path = Path(json_filename)

    if not json_path.exists():
        log(f"The JSON file {json_filename} could not be found.", success=False)
        return

    with file_lock:
        try:
            with json_path.open('r', encoding='utf-8') as f:
                json_data = json.load(f)
        except json.JSONDecodeError as e:
            log(f"Error decoding JSON file {json_filename}: {str(e)}", success=False)
            return

    # Parallel processing can occur here, but writing to the file needs locking
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_item = {executor.submit(process_item_safe, item): item for item in json_data}
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            try:
                updated_item = future.result()
                if updated_item:
                    update_sorted_series_item(updated_item)
            except Exception as exc:
                log(f'Item {item.get("Name", "Unknown")} generated an exception: {exc}', success=False)

    # Save missing folders at the end of processing
    save_missing_folders()

def process_item_safe(item: Dict) -> Dict:
    try:
        return process_item(item)
    except Exception as e:
        log(f"Error processing item {item.get('Name', 'Unknown')}: {str(e)}", success=False)
        return item

def process_item(item: Dict) -> Dict:
    clean_json_names(OUTPUT_FILENAME)

    #if 'OriginalTitle' in item and not all(ord(c) < 128 for c in item['OriginalTitle']):
    if USE_TMDB:
        media_type = 'tv' if 'Seasons' in item else 'movie'
        original_title = item.get('OriginalTitle', item.get('Name'))
        english_title = get_english_title(original_title, item.get('Year'), original_title, media_type)
        if english_title:
            item['EnglishTitle'] = english_title

    item_dir = directory_manager.get_item_directory(item)
    if not item_dir:
        return item

    updates = []

    main_poster_path = find_main_poster(item_dir)
    if main_poster_path:
        updates.append(
            (item['Id'], main_poster_path, f"{clean_name(item.get('Name'))} ({item.get('Year')})", 'Primary'))
    else:
        log(f"Main Cover not Found for item: {clean_name(item.get('Name'))} ({item.get('Year')})", success=False)
        missing_folders.append(f"Main Cover not Found: {item_dir / 'poster'}")

    backdrop_path = find_backdrop(item_dir)
    if backdrop_path:
        for x in range(0, 10):
            url = f"{JELLYFIN_URL}/Items/{item['Id']}/Images/Backdrop/0"
            headers = {'X-Emby-Token': API_KEY}
            response = requests.delete(url, headers=headers)
        updates.append((item['Id'], backdrop_path, f"{clean_name(item.get('Name'))} ({item.get('Year')})", 'Backdrop'))


    if 'Seasons' in item:
        updates.extend(process_seasons(item, item_dir))
    elif item.get('Type') in ['Movie', 'BoxSet']:
        if not main_poster_path:
            missing_folders.append(f"{item.get('Type')} Poster not Found: {item_dir / 'poster'}")

    # Perform Jellyfin updates
    for update in updates:
        update_jellyfin(*update)

    return item

def update_sorted_series_item(updated_item):
    sorted_series_path = Path(OUTPUT_FILENAME)
    if not sorted_series_path.exists():
        log(f"The file {OUTPUT_FILENAME} could not be found.", success=False)
        return

    # Synchronized access to the JSON file
    with file_lock:
        try:
            with sorted_series_path.open('r', encoding='utf-8') as f:
                sorted_series = json.load(f)

            # Update the series item in memory
            for i, item in enumerate(sorted_series):
                if item['Id'] == updated_item['Id']:
                    sorted_series[i] = updated_item
                    break

            # Write the updated JSON back to the file
            with sorted_series_path.open('w', encoding='utf-8') as f:
                json.dump(sorted_series, f, indent=4, ensure_ascii=False)

        except json.JSONDecodeError as e:
            log(f"Error decoding JSON in {OUTPUT_FILENAME}: {str(e)}", success=False)
            log(f"Error occurred at line {e.lineno}, column {e.colno}", success=False)
        except Exception as e:
            log(f"Error updating {OUTPUT_FILENAME}: {str(e)}", success=False)




def find_main_poster(item_dir: Path) -> Path:
    for poster_filename in ['poster.png', 'poster.jpeg', 'poster.jpg', 'poster.webp']:
        poster_path = item_dir / poster_filename
        if poster_path.exists():
            return poster_path
    return None


def process_seasons(item: Dict, item_dir: Path) -> List[Tuple]:
    updates = []
    for season_name, season_data in item.get('Seasons', {}).items():
        if 'Id' in season_data:
            season_number = season_name.split(" ")[-1]
            season_image_filename = f'Season{season_number.zfill(2)}'
            season_image_path = find_season_image(item_dir, season_image_filename)

            if season_image_path:
                updates.append((season_data['Id'], season_image_path,
                                f"{clean_name(item.get('Name'))} ({item.get('Year')}) - {season_name}", 'Primary'))
            else:
                log(f"Season image not found for item - {clean_name(item.get('Name'))} ({item.get('Year')}) - {season_name}",
                    success=False)
                missing_folders.append(f"Season Cover not Found: {item_dir / season_image_filename}")

            updates.extend(process_episodes(item, season_data, item_dir, season_number))

    return updates

def process_episodes(item: Dict, season_data: Dict, item_dir: Path, season_number: str) -> List[Tuple]:
    updates = []
    for episode_number, episode_id in season_data.get('Episodes', {}).items():
        if not episode_id or not episode_number.isdigit():
            log(f"Skipping invalid episode: S{season_number}E{episode_number} in {item.get('Name', 'Unknown Series')}", success=False)
            continue

        episode_image_filename = f'S{season_number.zfill(2)}E{episode_number.zfill(2)}'
        episode_image_path = find_episode_image(item_dir, episode_image_filename)

        if episode_image_path:
            updates.append((episode_id, episode_image_path, f"{clean_name(item.get('Name', 'Unknown'))} ({item.get('Year', 'Unknown')}) - S{season_number}E{episode_number}", 'Primary'))

    return updates

def find_file_with_extensions(directory: Path, filename: str, extensions: List[str]) -> Optional[Path]:
    for ext in extensions:
        file_path = directory / f"{filename}.{ext}"
        if file_path.exists():
            return file_path
    return None

def find_main_poster(item_dir: Path) -> Optional[Path]:
    return find_file_with_extensions(item_dir, "poster", ['png', 'jpeg', 'jpg', 'webp'])

def find_backdrop(item_dir: Path) -> Optional[Path]:
    return find_file_with_extensions(item_dir, "backdrop", ['png', 'jpg', 'jpeg', 'webp'])

def find_season_image(item_dir: Path, season_image_filename: str) -> Optional[Path]:
    return find_file_with_extensions(item_dir, season_image_filename, ['png', 'jpg', 'jpeg', 'webp'])

def find_episode_image(item_dir: Path, episode_image_filename: str) -> Optional[Path]:
    return find_file_with_extensions(item_dir, episode_image_filename, ['png', 'jpg', 'jpeg', 'webp'])

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
