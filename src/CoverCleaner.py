from pathlib import Path
import zipfile
import os
import re
import shutil
from typing import List, Optional
from PIL import Image
from datetime import datetime

from src.constants import RAW_COVER_DIR, COVER_DIR, CONSUMED_DIR, REPLACED_DIR, POSTER_DIR, COLLECTIONS_DIR
from src.utils import log
from src.updateCover import directory_manager

def is_valid_zip(zip_path: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.testzip()
        return True
    except zipfile.BadZipFile as e:
        log(f"Error: The file is not a valid ZIP file. {zip_path}: {e}", success=False)
    except PermissionError as e:
        log(f"Error: Permission denied. Unable to access the file. {zip_path}: {e}", success=False)
    except OSError as e:
        log(f"Error: OS error occurred. {zip_path}: {e}", success=False)
    except Exception as e:
        log(f"Error: An unexpected error occurred while checking ZIP file. {zip_path}: {e}", success=False)
    return False

def archive_existing_content(target_dir: Path):
    if not any(target_dir.iterdir()):  # Check if the directory is empty
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dir_name = target_dir.name
    zip_filename = f"{dir_name}_{timestamp}.zip"
    replaced_dir = Path(REPLACED_DIR) / dir_name
    replaced_dir.mkdir(parents=True, exist_ok=True)
    zip_path = replaced_dir / zip_filename

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in target_dir.rglob('*'):
            if file_path.is_file():
                rel_path = file_path.relative_to(target_dir)
                new_name = rename_file(file_path.name, dir_name)
                arcname = rel_path.parent / new_name
                zipf.write(file_path, arcname)

    # Delete contents of the target directory
    for item in target_dir.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

    log(f"Archived existing content: {zip_path}")


def rename_file(filename: str, dir_name: str) -> str:
    year_pattern = re.compile(r'\(\d{4}\)')
    lower_filename = filename.lower()

    if lower_filename == 'poster.jpg':
        if not year_pattern.search(dir_name):
            return f"{dir_name} Collection.jpg"
        return f"{dir_name}.jpg"
    elif lower_filename.startswith('season'):
        season_match = re.search(r'season(\d+)', lower_filename)
        if season_match:
            season_number = int(season_match.group(1))
            return f"{dir_name} - {'Specials' if season_number == 0 else f'Season {season_number:02d}'}.jpg"
    elif (match := re.match(r's(\d+)e(\d+)', lower_filename)):
        season_number, episode_number = map(int, match.groups())
        return f"{dir_name} - S{season_number:d} E{episode_number:02d}.jpg"
    elif lower_filename == 'backdrop.jpg':
        return f"{dir_name} - Backdrop.jpg"
    return filename

def organize_covers():
    files_to_process = get_files_to_process()
    if not files_to_process:
        log("No Files to process", success=False)
        return

    for file_path in files_to_process:
        process_file(file_path)

    # Refresh DirectoryManager after processing the file
    directory_manager.scan_directories()


def get_files_to_process() -> List[Path]:
    return list(Path(RAW_COVER_DIR).iterdir())

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
        has_collection = any("Collection" in filename for filename in extracted_files)

        processed_files = set()

        for filename in extracted_files:
            if filename in processed_files:
                continue

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
    name, identifier = extract_movie_info(filename)

    if identifier == "Collection" or "Collection" in filename:
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
    collection_name, _ = extract_movie_info(filename)
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
    name, identifier = extract_movie_info(image_path.name)

    if identifier == "Collection":
        collection_dir = Path(COLLECTIONS_DIR) / name
        collection_dir.mkdir(parents=True, exist_ok=True)
        target_filename = 'poster.jpg'
        target_path = collection_dir / target_filename
    else:
        movie_dir = Path(POSTER_DIR) / f"{name} ({identifier})"
        movie_dir.mkdir(parents=True, exist_ok=True)
        target_filename = 'poster.jpg'
        target_path = movie_dir / target_filename


    archive_existing_content(target_path.parent)

    shutil.copy2(image_path, target_path)

    if target_path.suffix.lower() != '.jpg':
        converted_path = convert_to_jpg(target_path)
        if converted_path:
            target_path = converted_path
            target_filename = converted_path.name

    log(f"Processed: {image_path.name} -> {target_path}", details=str(target_path))


def extract_movie_info(filename: str) -> tuple[str, str]:
    clean_filename = re.sub(r' - (Season \d+|Specials)\.jpg', '', filename)

    # Check for Collection first
    if "Collection" in clean_filename:
        collection_name = clean_filename.split("Collection")[0].strip()
        return collection_name, "Collection"

    movie_match = re.match(r'(.+?) \((\d{4})\)', clean_filename)
    if movie_match:
        return movie_match.groups()

    return clean_filename.split('(')[0].strip(), 'Unknown'

def convert_to_jpg(image_path: Path) -> Optional[Path]:
    try:
        with Image.open(image_path) as img:
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