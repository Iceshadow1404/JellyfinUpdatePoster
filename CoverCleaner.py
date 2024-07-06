from pathlib import Path
import zipfile
import re
import shutil
from typing import List, Dict, Optional
from PIL import Image
import json

from src.constants import RAW_COVER_DIR, COVER_DIR, CONSUMED_DIR, REPLACED_DIR, POSTER_DIR, COLLECTIONS_DIR
from src.utils import log


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
            process_zip_file(file_path)
        elif file_path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            process_image_file(file_path)

        move_to_consumed(file_path)
        log(f"Processed: {file_path.name} -> Consumed/{file_path.name}")
    except Exception as e:
        log(f"Error processing {file_path.name}: {e}", success=False)


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
    elif is_series:
        process_series_image(zip_ref, filename, processed_files)
    else:
        process_movie_image(zip_ref, filename, processed_files)


def process_series_image(zip_ref: zipfile.ZipFile, filename: str, processed_files: set):
    series_match = re.match(r'(.+?) \((\d{4})\)', filename)
    if series_match:
        series_name, series_year = series_match.groups()
        series_dir = Path(POSTER_DIR) / f"{series_name} ({series_year})"
        series_dir.mkdir(parents=True, exist_ok=True)

        season_match = re.match(r'.*Season (\d+)', filename)
        if season_match:
            season_number = int(season_match.group(1))
            target_filename = f'Season{season_number:02}.jpg'
        elif "Specials" in filename:
            target_filename = 'Season00.jpg'
        else:
            target_filename = 'poster.jpg'

        target_path = series_dir / target_filename
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
        move_to_replaced(target_path)

    with zip_ref.open(filename) as source, open(target_path, 'wb') as target:
        shutil.copyfileobj(source, target)

    log(f"Processed: {filename} -> {target_path}", details=str(target_path))
    processed_files.add(target_path)


def move_to_replaced(file_path: Path):
    replaced_subdir = Path(REPLACED_DIR) / file_path.parent.name
    replaced_subdir.mkdir(parents=True, exist_ok=True)
    replaced_filename = generate_unique_filename(replaced_subdir, file_path.name)
    new_path = replaced_subdir / replaced_filename
    file_path.rename(new_path)
    log(f"Moved existing file: {file_path} -> {new_path}")


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
        target_filename = f'poster{image_path.suffix.lower()}'
        target_path = movie_dir / target_filename

        if target_path.exists():
            move_to_replaced(target_path)

        shutil.copy2(image_path, target_path)

        if target_path.suffix.lower() != '.jpg':
            converted_path = convert_to_jpg(target_path)
            if converted_path:
                target_path = converted_path
                target_filename = converted_path.name

        log(f"Processed: {image_path.name} -> {target_path}", details=str(target_path))


def extract_movie_info(filename: str) -> tuple:
    movie_match = re.match(r'(.+?) \((\d{4})\)', filename)
    if movie_match:
        movie_name, movie_year = movie_match.groups()
    else:
        movie_name = filename.split('(')[0].strip()
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