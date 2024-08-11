from pathlib import Path
import zipfile
import os
import re
import shutil
from typing import List, Dict, Optional
from PIL import Image
import json
from datetime import datetime

from src.constants import RAW_COVER_DIR, COVER_DIR, CONSUMED_DIR, REPLACED_DIR, POSTER_DIR, COLLECTIONS_DIR
from src.utils import log
from src.config import JELLYFIN_URL, API_KEY, TMDB_API_KEY, USE_TMDB


def is_valid_zip(zip_path: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Try to read the contents of the ZIP file
            zip_ref.testzip()
        return True
    except zipfile.BadZipFile:
        return False
    except Exception as e:
        log(f"Error checking ZIP file {zip_path}: {e}", success=False)
        return False

def archive_existing_content(target_dir):
    if not os.listdir(target_dir):  # Check if the directory is empty
        return  # If empty, nothing to archive

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dir_name = os.path.basename(target_dir)
    zip_filename = f"{dir_name}_{timestamp}.zip"
    replaced_dir = os.path.join(REPLACED_DIR, dir_name)
    os.makedirs(replaced_dir, exist_ok=True)
    zip_path = os.path.join(replaced_dir, zip_filename)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(target_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_dir = os.path.relpath(root, target_dir)

                # Rename the file to match the expected input format
                if file.lower() == 'poster.jpg':
                    new_name = f"{dir_name}.jpg"
                elif file.lower().startswith('season'):
                    season_match = re.search(r'season(\d+)', file.lower())
                    if season_match:
                        season_number = int(season_match.group(1))
                        if season_number == 0:
                            new_name = f"{dir_name} - Specials.jpg"
                        else:
                            new_name = f"{dir_name} - Season {season_number:02d}.jpg"
                    else:
                        new_name = file
                elif re.match(r's\d+e\d+', file.lower()):
                    season_episode_match = re.match(r's(\d+)e(\d+)', file.lower())
                    if season_episode_match:
                        season_number = int(season_episode_match.group(1))
                        episode_number = int(season_episode_match.group(2))
                        new_name = f"{dir_name} - S{season_number:d} E{episode_number:02d}.jpg"
                    else:
                        new_name = file
                elif file.lower() == 'backdrop.jpg':
                    new_name = f"{dir_name} - Backdrop.jpg"
                else:
                    new_name = file

                if rel_dir == '.':
                    arcname = new_name
                else:
                    arcname = os.path.join(rel_dir, new_name)

                zipf.write(file_path, arcname)

    # Delete contents of the target directory
    for item in os.listdir(target_dir):
        item_path = os.path.join(target_dir, item)
        if os.path.isfile(item_path):
            os.unlink(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)

    log(f"Archived existing content: {zip_path}")

def organize_covers():
    files_to_process = get_files_to_process()
    if not files_to_process:
        log("No Files to process", success=False)
        return

    for file_path in files_to_process:
        process_file(file_path)


def get_files_to_process() -> List[Path]:
    return [item for item in Path(RAW_COVER_DIR).iterdir() if item.is_file()]

def process_file(file_path: Path):
    try:
        if file_path.suffix.lower() == '.zip':
            if is_valid_zip(file_path):
                process_zip_file(file_path)
            else:
                log(f"Invalid ZIP file detected: {file_path}. Deleting...", success=False)
                file_path.unlink()
                return
        elif file_path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            process_image_file(file_path)

        move_to_consumed(file_path)
        log(f"Processed: {file_path.name} -> Consumed/{file_path.name}")
    except Exception as e:
        log(f"Error processing {file_path.name}: {e}", success=False)

def process_zip_file(zip_path: Path):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        extracted_files = [file_info.filename for file_info in zip_ref.infolist()]
        is_series = any(re.match(r'.*Season (\d+)', filename) or "Specials" in filename or re.match(r'.*S\d+E\d+', filename) for filename in extracted_files)
        has_collection = any("Collection" in filename or "Collections" in filename for filename in extracted_files)

        processed_files = set()

        for filename in extracted_files:
            if filename in processed_files:
                continue

            file_info = zip_ref.getinfo(filename)
            file_ext = Path(filename).suffix.lower()

            if file_ext in ('.png', '.jpg', '.jpeg', '.webp'):
                process_zip_image(zip_ref, filename, is_series, has_collection, processed_files)

def move_to_consumed(file_path: Path):
    consumed_dir = Path(CONSUMED_DIR)
    consumed_dir.mkdir(parents=True, exist_ok=True)
    new_filename = generate_unique_filename(consumed_dir, file_path.name)
    consumed_path = consumed_dir / new_filename

    try:
        shutil.copy2(file_path, consumed_path)  # Copy the file
        file_path.unlink()  # Delete the original file
        log(f"Moved to consumed: {file_path} -> {consumed_path}")
    except Exception as e:
        log(f"Error moving file to consumed: {e}", success=False)
        # If copying fails, we don't want to delete the original
        if consumed_path.exists():
            consumed_path.unlink()

def process_zip_file(zip_path: Path):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        extracted_files = [file_info.filename for file_info in zip_ref.infolist()]
        is_series = any(re.match(r'.*Season (\d+)', filename) or "Specials" in filename for filename in extracted_files)
        has_collection = any("Collection" in filename or "Collections" in filename for filename in extracted_files)

        processed_files = set()

        for filename in extracted_files:
            if filename in processed_files:
                continue

            file_info = zip_ref.getinfo(filename)
            file_ext = Path(filename).suffix.lower()

            if file_ext in ('.png', '.jpg', '.jpeg', '.webp'):
                process_zip_image(zip_ref, filename, is_series, has_collection, processed_files)

def process_zip_image(zip_ref: zipfile.ZipFile, filename: str, is_series: bool, has_collection: bool,
                      processed_files: set):
    if "Collection" in filename:
        process_collection_image(zip_ref, filename, processed_files)
    elif "Backdrop" in filename:
        process_backdrop_image(zip_ref, filename, processed_files)
    elif is_series or " S" in filename and " E" in filename:
        process_series_image(zip_ref, filename, processed_files)
    else:
        process_movie_image(zip_ref, filename, processed_files)

def process_series_image(zip_ref: zipfile.ZipFile, filename: str, processed_files: set):
    series_match = re.match(r'(.+?) \((\d{4})\)', filename)
    if series_match:
        series_name, series_year = series_match.groups()
        series_dir = Path(POSTER_DIR) / f"{series_name} ({series_year})"
        series_dir.mkdir(parents=True, exist_ok=True)

        season_match = re.search(r'Season (\d+)', filename)
        episode_match = re.search(r'S(\d+) E(\d+)', filename)

        if 'Specials' in filename or 'Season 0' in filename:
            target_filename = 'Season00.jpg'
        elif season_match:
            season_number = int(season_match.group(1))
            target_filename = f'Season{season_number:02d}.jpg'
        elif episode_match:
            season_number = int(episode_match.group(1))
            episode_number = int(episode_match.group(2))
            target_filename = f'S{season_number:02d}E{episode_number:02d}.jpg'
        else:
            target_filename = 'poster.jpg'

        target_path = series_dir / target_filename
        process_target_file(zip_ref, filename, target_path, processed_files)

def process_backdrop_image(zip_ref: zipfile.ZipFile, filename: str, processed_files: set):
    backdrop_match = re.match(r'(.+?) \((\d{4})\) - Backdrop', filename)
    if backdrop_match:
        name, year = backdrop_match.groups()
        media_dir = Path(POSTER_DIR) / f"{name} ({year})"
        media_dir.mkdir(parents=True, exist_ok=True)

        target_filename = 'backdrop.jpg'
        target_path = media_dir / target_filename
        process_target_file(zip_ref, filename, target_path, processed_files)

def process_movie_image(zip_ref: zipfile.ZipFile, filename: str, processed_files: set):
    movie_match = re.match(r'(.+?) \((\d{4})\)', filename)
    if movie_match:
        movie_name, movie_year = movie_match.groups()
        movie_dir = Path(POSTER_DIR) / f"{movie_name} ({movie_year})"
        movie_dir.mkdir(parents=True, exist_ok=True)

        target_filename = 'poster.jpg' if "Season" not in filename and "Specials" not in filename else f"{Path(filename).stem}.jpg"
        target_path = movie_dir / target_filename
        process_target_file(zip_ref, filename, target_path, processed_files)

def process_collection_image(zip_ref: zipfile.ZipFile, filename: str, processed_files: set):
    collection_match = re.match(r'(.+?) Collection', filename)
    if collection_match:
        collection_name = collection_match.group(1)
        collection_dir = Path(COLLECTIONS_DIR) / collection_name
        collection_dir.mkdir(parents=True, exist_ok=True)

        target_filename = 'poster.jpg'
        target_path = collection_dir / target_filename
        process_target_file(zip_ref, filename, target_path, processed_files)

def process_target_file(zip_ref: zipfile.ZipFile, filename: str, target_path: Path, processed_files: set):
    if target_path.exists() and target_path not in processed_files:
        archive_existing_content(target_path.parent)

    with zip_ref.open(filename) as source, open(target_path, 'wb') as target:
        shutil.copyfileobj(source, target)

    log(f"Processed: {filename} -> {target_path}", details=str(target_path))
    processed_files.add(target_path)

def generate_unique_filename(directory: Path, filename: str) -> str:
    base_name, ext = filename.rsplit('.', 1)
    counter = 1
    new_filename = filename
    while (directory / new_filename).exists():
        new_filename = f"{base_name}_{counter}.{ext}"
        counter += 1
    return new_filename

def process_image_file(image_path: Path):
    with Image.open(image_path) as img:
        movie_name, movie_year = extract_movie_info(image_path.name)
        movie_dir = Path(POSTER_DIR) / f"{movie_name} ({movie_year})"
        movie_dir.mkdir(parents=True, exist_ok=True)

        # Archive existing content, if any
        archive_existing_content(movie_dir)

        target_filename = f'poster{image_path.suffix.lower()}'
        target_path = movie_dir / target_filename

        shutil.copy2(image_path, target_path)

        if target_path.suffix.lower() != '.jpg':
            converted_path = convert_to_jpg(target_path)
            if converted_path:
                target_path = converted_path
                target_filename = converted_path.name

        log(f"Processed: {image_path.name} -> {target_path}", details=str(target_path))

def extract_movie_info(filename: str) -> tuple:
    # Remove any season or special information from the filename
    clean_filename = re.sub(r' - (Season \d+|Specials)\.jpg', '', filename)

    movie_match = re.match(r'(.+?) \((\d{4})\)', clean_filename)
    if movie_match:
        movie_name, movie_year = movie_match.groups()
    else:
        movie_name = clean_filename.split('(')[0].strip()
        movie_year = 'Unknown'
    return movie_name, movie_year

def convert_to_jpg(image_path: Path) -> Optional[Path]:
    try:
        img = Image.open(image_path)
        if img.format != 'JPEG':
            jpg_path = image_path.with_suffix('.jpg')
            img.convert('RGB').save(jpg_path, 'JPEG')
            image_path.unlink()
            log(f"Converted {image_path} to JPG format and deleted original.")
            return jpg_path
    except Exception as e:
        log(f"Error converting {image_path} to JPG: {e}", success=False)
    return None


if __name__ == "__main__":
    organize_covers()