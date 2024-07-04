import asyncio
import aiohttp
from base64 import b64encode
from typing import List, Dict, Tuple
from pathlib import Path

from src.config import JELLYFIN_URL, API_KEY
from src.utils import log, get_content_type

COVER_DIR = Path('./Cover')
POSTER_DIR = COVER_DIR / 'Poster'
COLLECTIONS_DIR = COVER_DIR / 'Collections'

missing_folders: List[str] = []

def clean_json_names(json_filename: str):
    json_path = Path(json_filename)

    if not json_path.exists():
        log(f"The JSON file {json_filename} could not be found.", success=False)
        log("Don't panic if this is your first time using this script; just wait 60 seconds for new instructions")
        return

    with json_path.open('r', encoding='utf-8') as f:
        json_data = json.load(f)

    for series in json_data:
        if 'Name' in series:
            series['Name'] = clean_name(series['Name'])
        if 'OriginalTitle' in series:
            series['OriginalTitle'] = clean_name(series['OriginalTitle'])

    with json_path.open('w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=4)

def clean_name(name: str) -> str:
    return name.replace(':', '').replace('&', '').replace("'", '').replace("!", '')

def assign_images_and_update_jellyfin(json_filename: str):
    json_path = Path(json_filename)

    if not json_path.exists():
        log(f"The JSON file {json_filename} could not be found.", success=False)
        return

    with json_path.open('r', encoding='utf-8') as f:
        json_data = json.load(f)

    for item in json_data:
        process_item(item)

    log(f"Processing completed for {json_filename}")
    log("Updated all posters")

def process_item(item: Dict):
    item_name = item.get('Name', '').strip()
    item_original_title = item.get('OriginalTitle', item_name).strip()
    item_year = item.get('Year')
    item_id = item.get('Id')
    item_type = item.get('Type')

    if not all([item_original_title, item_year, item_id]):
        log(f"Invalid data found for item: {item}. Skipping.", success=False)
        return

    item_dir = get_item_directory(item_type, item_name, item_original_title, item_year)
    if not item_dir:
        return

    main_poster_path = find_main_poster(item_dir)
    if main_poster_path:
        update_jellyfin(item_id, main_poster_path, f"{item_original_title} ({item_year})")
    else:
        log(f"Main poster not found for item: {item_original_title} ({item_year})", success=False)

    process_seasons(item, item_dir, item_original_title, item_year)

def get_item_directory(item_type: str, item_name: str, item_original_title: str, item_year: str) -> Path:
    if item_type == "BoxSet":
        item_dir = COLLECTIONS_DIR / item_name
    else:
        item_dir = POSTER_DIR / f"{item_original_title} ({item_year})"
        if not item_dir.exists():
            item_dir = POSTER_DIR / f"{item_name} ({item_year})"

    if not item_dir.exists():
        missing_folder = f"Folder not found: {item_dir}"
        log(missing_folder, success=False)
        missing_folders.append(missing_folder)
        return None

    return item_dir

def find_main_poster(item_dir: Path) -> Path:
    for poster_filename in ['poster.png', 'poster.jpeg', 'poster.jpg', 'poster.webp']:
        poster_path = item_dir / poster_filename
        if poster_path.exists():
            return poster_path
    return None

def process_seasons(item: Dict, item_dir: Path, item_original_title: str, item_year: str):
    for key, image_id in item.items():
        if key.startswith("Season") and image_id:
            season_number = key.split(" ")[-1]
            season_image_filename = f'Season{season_number.zfill(2)}'
            season_image_path = find_season_image(item_dir, season_image_filename)

            if not season_image_path:
                log(f"Season image not found for item - {item_original_title} ({item_year}) - {key}", success=False)
                continue

            update_jellyfin(image_id, season_image_path, f"{item_original_title} ({item_year}) - {key}")

def find_season_image(item_dir: Path, season_image_filename: str) -> Path:
    for ext in ['png', 'jpg', 'jpeg', 'webp']:
        season_image_path = item_dir / f"{season_image_filename}.{ext}"
        if season_image_path.exists():
            return season_image_path
    return None

async def update_jellyfin_async(session: aiohttp.ClientSession, id: str, image_path: Path, item_name: str):
    endpoint = f'/Items/{id}/Images/Primary/0'
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
        async with session.post(url, headers=headers, data=image_base64) as response:
            await response.raise_for_status()
        log(f'Updated image for {item_name} successfully.')
    except aiohttp.ClientResponseError as e:
        log(f'Error updating image for {item_name}. Status Code: {e.status}', success=False)
        log(f'Response: {e.message}', success=False)

if __name__ == "__main__":
    # This block can be used for testing the module independently
    json_filename = 'sorted_series.json'
    clean_json_names(json_filename)
    assign_images_and_update_jellyfin(json_filename)