import os
import zipfile
import re
import shutil
import requests
from rapidfuzz import fuzz
import logging
from PIL import Image
from datetime import datetime, timedelta
import json
from pathlib import Path

from src.constants import LANGUAGE_DATA_FILENAME, RAW_COVER_DIR, COVER_DIR, COLLECTIONS_DIR, CONSUMED_DIR, \
    NO_MATCH_FOLDER, REPLACED_DIR, POSTER_DIR

logger = logging.getLogger(__name__)

LAST_TIMESTAMP = None
TIME_WINDOW = timedelta(seconds=60)

def load_language_data():
    try:
        with open(LANGUAGE_DATA_FILENAME, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Language data file not found: {LANGUAGE_DATA_FILENAME}")
        return {}
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from language data file: {LANGUAGE_DATA_FILENAME}")
        return {}

def convert_to_jpg(file_path):
    """Convert image to JPG format if it's not already."""
    filename, file_extension = os.path.splitext(file_path)
    if file_extension.lower() not in ['.jpg', '.jpeg']:
        try:
            with Image.open(file_path) as img:
                # Remove XMP metadata to prevent "XMP data is too long" error
                img.info.pop('xmp', None)

                rgb_img = img.convert('RGB')
                new_file_path = f"{filename}.jpg"
                rgb_img.save(new_file_path, 'JPEG')
            os.remove(file_path)
            return new_file_path
        except Exception as e:
            logger.error(f"Error converting {file_path} to JPG: {str(e)}")
            # If conversion fails, return the original file path
            return file_path
    elif file_extension.lower() == '.jpeg':
        new_file_path = f"{filename}.jpg"
        os.rename(file_path, new_file_path)
        return new_file_path
    return file_path


def find_collection_match(clean_name, language_data):
    """Find a matching collection in language data."""
    logger.debug(f"Searching for collection match: {clean_name}")

    # Remove 'Collection' from the clean_name if present for better matching
    clean_name = re.sub(r'\s*collection\s*$', '', clean_name, flags=re.IGNORECASE)

    best_match = None
    best_score = 0

    collections = language_data.get('collections', {})
    for collection_id, collection_data in collections.items():
        if collection_id == 'last_updated':
            continue

        # Compare with each title in the titles array
        for title in collection_data.get('titles', []):
            # Clean up the comparison title as well
            clean_title = re.sub(r'\s*collection\s*$', '', title, flags=re.IGNORECASE)
            score = fuzz.ratio(clean_name.lower(), clean_title.lower(), score_cutoff=0)

            if score > best_score:
                best_score = score
                best_match = {
                    'id': collection_id,
                    'name': collection_data.get('extracted_title', ''),
                    'year': collection_data.get('year'),
                    'tmdb_id': collection_id,
                    'extracted_title': collection_data.get('extracted_title', '')
                }

        # Also compare with extracted_title
        clean_extracted = re.sub(r'\s*collection\s*$', '',
                                 collection_data.get('extracted_title', ''),
                                 flags=re.IGNORECASE)
        score = fuzz.ratio(clean_name.lower(), clean_extracted.lower(), score_cutoff=0)

        if score > best_score:
            best_score = score
            best_match = {
                'id': collection_id,
                'name': collection_data.get('extracted_title', ''),
                'year': collection_data.get('year'),
                'tmdb_id': collection_id,
                'extracted_title': collection_data.get('extracted_title', '')
            }

    if best_score >= 90:
        logger.info(f"Found collection match: {best_match['name']} (Score: {best_score})")
        return best_match

    logger.warning(f"No collection match found for: {clean_name}")
    return None

def process_collection(file_path, language_data):
    filename = os.path.basename(file_path)
    logger.info(f"Processing collection image file: {filename}")

    # Determine if this is a background/backdrop image
    is_background = any(term in filename.lower() for term in ['backdrop', 'background'])

    # Clean name once and reuse
    base_name = re.sub(r'\s*-?\s*(Backdrop|Background)', '', filename, flags=re.IGNORECASE)
    clean_name = clean_name_for_folder(os.path.splitext(base_name)[0])
    matched_collection = find_collection_match(clean_name, language_data)

    if matched_collection:
        # Use the extracted title from the match
        extracted_title = matched_collection['extracted_title']
        folder_name = sanitize_folder_name(extracted_title)
        new_folder = os.path.join(COLLECTIONS_DIR, folder_name)
        os.makedirs(new_folder, exist_ok=True)

        # Determine the appropriate filename based on whether it's a background
        new_filename = "background.jpg" if is_background else "poster.jpg"
        new_file_path = os.path.join(new_folder, new_filename)

        # Archive existing content if necessary
        if os.path.exists(new_file_path):
            archive_existing_content(Path(new_folder))

        # Move the file to the new folder and rename it
        shutil.move(file_path, new_file_path)
        logger.info(f"Collection file moved and renamed to: {new_file_path}")

        return new_file_path, language_data
    else:
        # Process unmatched collection
        timestamp = get_timestamp_folder()
        no_match_folder = os.path.join(NO_MATCH_FOLDER, 'Collections', clean_name, timestamp)
        os.makedirs(no_match_folder, exist_ok=True)

        new_file_path = os.path.join(no_match_folder, os.path.basename(file_path))
        shutil.move(file_path, new_file_path)

        logger.info(f"Unmatched collection moved to: {new_file_path}")
        return new_file_path, language_data


def clean_name(filename):
    """Clean the filename by removing season, episode, specials information, but preserving the year."""
    logger.debug(f"Cleaning name for: {filename}")
    name = os.path.splitext(filename)[0]
    name = re.sub(r'\s*-\s*S\d+\s*E\d+', '', name)
    name = re.sub(r'\s*-\s*Season\s*\d+', '', name)
    name = re.sub(r'\s*-\s*Specials', '', name)
    name = re.sub(r'\s*-\s*Backdrop', '', name)
    name = re.sub(r'\s*-\s*Background', '', name)
    name = re.sub(r':', '', name)
    cleaned_name = name.strip()
    logger.debug(f"Cleaned name: {cleaned_name}")
    return cleaned_name


def clean_name_for_folder(name):
    """Remove unwanted characters from the name while preserving content in parentheses for collections."""
    # Remove any parentheses that contain only a year
    cleaned = re.sub(r'\s*\(\d{4}\)', '', name)
    # Remove any non-alphanumeric characters except dash, underscore, dot, space, and parentheses
    cleaned = re.sub(r'[^\w\-_\. ()]', '', cleaned)
    # Remove trailing dots
    cleaned = cleaned.rstrip('.')
    return cleaned.strip()

def get_series_name(filename):
    """Extract the series name and year from the filename."""
    # Remove season and episode information
    name = re.sub(r'\s*-\s*S\d+\s*E\d+', '', filename)
    name = re.sub(r'\s*-\s*Season\s*\d+', '', name)
    # Remove any mention of 'Specials'
    name = re.sub(r'\s*-\s*Specials', '', name, flags=re.IGNORECASE)
    # Extract year if present
    year_match = re.search(r'\s*\((\d{4})\)', name)
    year = year_match.group(1) if year_match else None
    # Remove year from name
    name = re.sub(r'\s*\(\d{4}\)', '', name)
    # Remove any mention of 'backdrop' or 'background'
    name = re.sub(r'\s*-?\s*(Backdrop|Background)', '', name, flags=re.IGNORECASE)
    # Remove file extension
    name = os.path.splitext(name)[0]
    return clean_name_for_folder(name), year

def get_timestamp_folder():
    global LAST_TIMESTAMP
    current_time = datetime.now()

    if LAST_TIMESTAMP is None or (current_time - LAST_TIMESTAMP) > TIME_WINDOW:
        LAST_TIMESTAMP = current_time
        return LAST_TIMESTAMP.strftime("%Y-%m-%d_%H-%M-%S")
    else:
        return LAST_TIMESTAMP.strftime("%Y-%m-%d_%H-%M-%S")

def extract_zip(zip_path, extract_to):
    """Extract contents of a ZIP file."""
    logger.info(f"Extracting ZIP file: {zip_path}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    logger.info(f"ZIP file extracted to: {extract_to}")


def find_match(clean_name, language_data):
    """Find a matching item in language data, considering the year if available."""
    logger.debug(f"Searching for match: {clean_name}")

    # Extract year from clean_name if present
    year_match = re.search(r'\((\d{4})\)', clean_name)
    file_year = int(year_match.group(1)) if year_match else None
    clean_name_without_year = re.sub(r'\s*\(\d{4}\)', '', clean_name).strip()

    best_match = None
    best_score = 0

    # Search in both movies and TV shows
    for category in ['movies', 'tv']:
        for item_id, item_data in language_data.get(category, {}).items():
            if item_id == 'last_updated':
                continue

            extracted_title = item_data.get('extracted_title', '')
            original_title = item_data.get('originaltitle', '')
            item_year = item_data.get('year')

            # Compare with extracted_title
            extracted_title_score = compare_titles(clean_name_without_year, extracted_title, item_year, file_year)

            # Compare with original_title
            original_title_score = compare_titles(clean_name_without_year, original_title, item_year, file_year) if original_title else 0

            # Compare with all titles in the array
            title_scores = [compare_titles(clean_name_without_year, title, item_year, file_year) for title in item_data.get('titles', [])]

            # Get the maximum score from all comparisons
            max_score = max([extracted_title_score, original_title_score] + title_scores)

            if max_score > best_score:
                best_score = max_score
                best_match = {
                    'id': item_id,
                    'extracted_title': extracted_title,
                    'original_title': original_title,
                    'year': item_year,
                    'type': category  # Add type information to help with processing
                }

    if best_score >= 95:
        return best_match

    logger.warning(f"No match found for: {clean_name}")
    return None


def compare_titles(clean_name, item_name, item_year, file_year):
    """Compare titles considering the year if available."""
    name_ratio = fuzz.ratio(clean_name.lower(), item_name.lower(), score_cutoff=0)

    if file_year and item_year:
        if file_year == item_year:
            return name_ratio + 10  # Boost score if years match
        else:
            return max(0, name_ratio - 10)  # Penalize score if years don't match

    return name_ratio


def sanitize_folder_name(folder_name):
    """Remove invalid characters from folder name."""
    invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '&', "'", '!', '?', '[', ']']
    for char in invalid_chars:
        folder_name = folder_name.replace(char, '')
    return folder_name.strip()

def is_collection(filename):
    """Determine if a file is part of a collection based on its filename."""
    # Expand the search to include more collection-related keywords
    collection_keywords = ['collection', 'filmreihe', 'box set', 'series', 'anthology']
    for keyword in collection_keywords:
        if keyword in filename.lower():
            return True
    return False


def process_image_file(file_path, language_data):
    """Process an individual image file."""
    filename = os.path.basename(file_path)
    logger.debug(f"Processing image file: {filename}")

    # Convert the image to JPG format
    file_path = convert_to_jpg(file_path)
    filename = os.path.basename(file_path)

    # First check if it's a collection
    if is_collection(filename):
        logger.info(f"Detected collection file: {filename}")
        return process_collection(file_path, language_data)

    # Check if it's a background/backdrop image
    is_background = any(term in filename.lower() for term in ['backdrop', 'background'])
    clean_name_result = clean_name(filename)
    year_match = re.search(r'\((\d{4})\)', filename)
    year = year_match.group(1) if year_match else None

    matched_item = find_match(clean_name_result, language_data)

    if matched_item:
        extracted_title = matched_item['extracted_title']
        original_title = matched_item.get('original_title', '')
        year = matched_item.get('year', '')

        display_title = (
            original_title if original_title and original_title != extracted_title and not contains_non_ascii(
                original_title)
            else extracted_title
        )

        folder_name = f"{display_title} ({year})" if year else display_title
        folder_name = sanitize_folder_name(folder_name)

        new_folder = os.path.join(POSTER_DIR, folder_name)
        os.makedirs(new_folder, exist_ok=True)

        if is_background:
            new_filename = "background.jpg"
        elif re.search(r'S\d+\s*E\d+', filename):
            season_episode = re.search(r'S(\d+)\s*E(\d+)', filename)
            new_filename = f"S{int(season_episode.group(1)):02d}E{int(season_episode.group(2)):02d}.jpg"
        elif 'Season' in filename:
            season_number = re.search(r'Season\s*(\d+)', filename)
            new_filename = f"Season{int(season_number.group(1)):02d}.jpg"
        elif 'Specials' in filename:
            new_filename = "Season00.jpg"
        else:
            new_filename = "poster.jpg"

        new_file_path = os.path.join(new_folder, new_filename)

        if os.path.exists(new_file_path):
            archive_existing_content(Path(new_folder))

        shutil.move(file_path, new_file_path)
        return True

    else:
        series_name, file_year = get_series_name(filename)
        year_to_use = year or file_year
        timestamp = get_timestamp_folder()

        # Create base folder name with year if available
        base_name = f"{series_name} ({year_to_use})" if year_to_use else series_name

        # For background images, append " - Background" to the filename
        if is_background and not filename.lower().endswith(' - background.jpg'):
            name_without_ext, ext = os.path.splitext(base_name)
            new_filename = f"{name_without_ext} - Background.jpg"
        else:
            new_filename = filename

        no_match_folder = Path(NO_MATCH_FOLDER) / 'Poster' / base_name / timestamp
        no_match_folder.mkdir(parents=True, exist_ok=True)

        new_file_path = no_match_folder / new_filename
        shutil.move(file_path, new_file_path)

        logger.info(f"File moved to No-Match folder: {new_file_path}")
        return True


def contains_non_ascii(s):
    return any(ord(char) > 127 for char in s)


def process_zip_file(zip_path, language_data):
    """Process a ZIP file containing multiple image files."""
    logger.info(f"Processing ZIP file: {zip_path}")
    temp_dir = os.path.join(RAW_COVER_DIR, 'temp')
    os.makedirs(temp_dir, exist_ok=True)

    try:
        extract_zip(zip_path, temp_dir)

        all_processed = True
        for extracted_file in os.listdir(temp_dir):
            extracted_file_path = os.path.join(temp_dir, extracted_file)
            if extracted_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                converted_file_path = convert_to_jpg(extracted_file_path)
                if not process_image_file(converted_file_path, language_data):
                    all_processed = False

        if all_processed:
            # Only move to consumed if all files were processed successfully
            move_to_consumed(zip_path)

    except Exception as e:
        logger.error(f"Error processing ZIP file {zip_path}: {str(e)}")
        all_processed = False
    finally:
        # Clean up temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    return all_processed


def move_to_consumed(file_path):
    """Move file to Consumed folder, handling existing files, unless it's a rematch file."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found, skipping move to Consumed: {file_path}")
        return False

    # Check if this is a rematch file
    if "_REMATCH_MARKER" in file_path:
        try:
            os.remove(file_path)
            logger.info(f"Deleted rematch file: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting rematch file: {str(e)}")
            return False

    os.makedirs(CONSUMED_DIR, exist_ok=True)
    filename = os.path.basename(file_path)
    consumed_file_path = os.path.join(CONSUMED_DIR, filename)

    # If file already exists, add numbering
    counter = 1
    while os.path.exists(consumed_file_path):
        name, ext = os.path.splitext(filename)
        new_filename = f"{name}_{counter}{ext}"
        consumed_file_path = os.path.join(CONSUMED_DIR, new_filename)
        counter += 1

    try:
        shutil.move(file_path, consumed_file_path)
        logger.debug(f"File moved to Consumed folder: {consumed_file_path}")
        return True
    except Exception as e:
        logger.error(f"Error moving file to Consumed folder: {str(e)}")
        return False


def archive_existing_content(target_dir: Path):
    if not any(target_dir.iterdir()):  # Check if the directory is empty
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dir_name = target_dir.name

    # Determine if it's a collection or a regular
    replaced_subdir = 'Collections' if is_collection(dir_name) else 'Poster'

    # Create a subfolder for this specific item
    replaced_dir = Path(REPLACED_DIR) / replaced_subdir / dir_name
    replaced_dir.mkdir(parents=True, exist_ok=True)

    # Create a timestamped subfolder for this archive
    archive_subfolder = replaced_dir / timestamp
    archive_subfolder.mkdir(parents=True, exist_ok=True)

    for file_path in target_dir.rglob('*'):
        if file_path.is_file():
            new_name = rename_file_for_archive(file_path.name, dir_name)
            new_file_path = archive_subfolder / new_name
            shutil.copy2(file_path, new_file_path)  # Use copy2 to preserve metadata

    # Delete contents of the target directory
    for item in target_dir.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

    logger.info(f"Archived existing content: {archive_subfolder}")

def rename_file_for_archive(filename: str, dir_name: str) -> str:
    year_pattern = re.compile(r'\(\d{4}\)')
    lower_filename = filename.lower()

    if lower_filename == 'poster.jpg':
        if 'collection' in dir_name.lower():
            return f"{dir_name}.jpg"
        elif not year_pattern.search(dir_name):
            return f"{dir_name} Collection.jpg"
        return f"{dir_name}.jpg"
    elif lower_filename.startswith('season'):
        season_match = re.search(r'season(\d+)', lower_filename)
        if season_match:
            season_number = int(season_match.group(1))
            return f"{dir_name} - {'Specials' if season_number == 0 else f'Season {season_number:02d}'}.jpg"
    elif (match := re.match(r's(\d+)e(\d+)', lower_filename)):
        season_number, episode_number = map(int, match.groups())
        return f"{dir_name} - S{season_number:02d}E{episode_number:02d}.jpg"
    elif lower_filename in ['backdrop.jpg', 'background.jpg']:
        return f"{dir_name} - Backdrop.jpg"
    return filename


def consolidate_series_folders(base_path=POSTER_DIR):
    logger.debug(f"Starting consolidate_series_folders for path: {base_path}")

    # Ensure base_path is a Path object and exists
    base_path = Path(NO_MATCH_FOLDER + '/Poster')

    # Create the path if it doesn't exist
    base_path.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Absolute path being used: {base_path.resolve()}")

    # Find all series folders
    try:
        series_folders = [f for f in os.listdir(base_path) if (base_path / f).is_dir()]
        logger.debug(f"Found {len(series_folders)} series folders")
        logger.debug(f"Folders: {series_folders}")
    except Exception as e:
        logger.error(f"Error listing directories in {base_path}: {e}")
        return

    # Group folders by base series name (without year)
    series_groups = {}
    for folder in series_folders:
        # Extract base name without year
        base_name = re.sub(r'\s*\(\d{4}\)', '', folder).strip()
        logger.debug(f"Processing folder: {folder}, base name: {base_name}")

        if base_name not in series_groups:
            series_groups[base_name] = []
        series_groups[base_name].append(folder)

    # Log series groups
    logger.debug("Series Groups:")
    for base_name, folders in series_groups.items():
        logger.debug(f"{base_name}: {folders}")
        if len(folders) > 1:
            # Sort folders to prioritize the one with year
            sorted_folders = sorted(folders, key=lambda x: '(' in x, reverse=True)

            # Use the first (preferably year-containing) folder as the target
            target_folder = sorted_folders[0]
            target_path = base_path / target_folder

            # Merge other folders into the target folder
            for source_folder in sorted_folders[1:]:
                source_path = base_path / source_folder

                target_timestamps = [
                    datetime.strptime(d, "%Y-%m-%d_%H-%M-%S")
                    for d in os.listdir(target_path)
                    if re.match(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}', d)
                ]

                for item in os.listdir(source_path):
                    # Check if item is a timestamp folder
                    if re.match(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}', item):
                        source_timestamp = datetime.strptime(item, "%Y-%m-%d_%H-%M-%S")

                        # Check if any target timestamp is within 60 seconds
                        if any((abs(source_timestamp - ts).total_seconds() <= 60) for ts in target_timestamps):
                            source_items_path = source_path / item
                            for subitem in os.listdir(source_items_path):
                                target_timestamp_path = target_path / item
                                target_timestamp_path.mkdir(parents=True, exist_ok=True)

                                target_subitem_path = target_timestamp_path / subitem
                                source_subitem_path = source_items_path / subitem

                                shutil.move(str(source_subitem_path), str(target_subitem_path))

                            # Remove the empty source timestamp folder
                            source_items_path.rmdir()

                # Remove the empty source folder if it's now empty
                if not os.listdir(source_path):
                    source_path.rmdir()

                logger.info(f"Merged folder {source_folder} into {target_folder}")



def cover_cleaner(language_data):
    global LAST_TIMESTAMP
    LAST_TIMESTAMP = None

    files = os.listdir(RAW_COVER_DIR)

    if files:
        for filename in files:
            if filename == '.DS_Store':
                continue

            file_path = os.path.join(RAW_COVER_DIR, filename)
            logger.info(f"Processing file: {filename}")

            try:
                if filename.endswith('.zip'):
                    process_zip_file(file_path, language_data)
                elif filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    original_file_path = file_path
                    destination_path = os.path.join(CONSUMED_DIR, os.path.basename(original_file_path))

                    shutil.copy(original_file_path, destination_path)
                    logger.debug(f"File moved to {destination_path}")

                    if process_image_file(file_path, language_data):
                        if os.path.exists(file_path):
                            move_to_consumed(file_path)
                    else:
                        logger.warning(f"Failed to process image file: {filename}")
            except Exception as e:
                logger.error(f"Error processing {filename}: {str(e)}")
                if os.path.exists(original_file_path):
                    move_to_consumed(original_file_path)

            cleanup_empty_folders()
    else:
        logger.info('No files found in the folder.')

def cleanup_empty_folders():
    """Remove empty folders in the NO_MATCH_FOLDER directory."""
    for root, dirs, files in os.walk(NO_MATCH_FOLDER, topdown=False):
        for dir in dirs:
            dir_path = os.path.join(root, dir)
            if not os.listdir(dir_path):
                os.rmdir(dir_path)
                logger.info(f"Removed empty folder: {dir_path}")

if __name__ == "__main__":
    cover_cleaner(load_language_data())
