import os
import zipfile
import re
import shutil
import requests
from fuzzywuzzy import fuzz
import logging
from PIL import Image
from datetime import datetime
from pathlib import Path
import json
from datetime import datetime, timedelta

from src.updateCover import UpdateCover
from src.rematchNoMatchFolder import FolderMatcher
from src.constants import LANGUAGE_DATA_FILENAME, RAW_COVER_DIR, COVER_DIR, COLLECTIONS_DIR, CONSUMED_DIR, \
    NO_MATCH_FOLDER, REPLACED_DIR, POSTER_DIR

logger = logging.getLogger(__name__)
updater = UpdateCover()

LAST_TIMESTAMP = None
TIME_WINDOW = timedelta(seconds=10)

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
                rgb_img = img.convert('RGB')
                new_file_path = f"{filename}.jpg"
                rgb_img.save(new_file_path, 'JPEG')
            os.remove(file_path)
            return new_file_path
        except Exception as e:
            logger.error(f"Error converting {file_path} to JPG: {str(e)}")
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
            score = fuzz.ratio(clean_name.lower(), clean_title.lower())

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
        score = fuzz.ratio(clean_name.lower(), clean_extracted.lower())

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
    """Process a collection image file."""
    filename = os.path.basename(file_path)
    logger.info(f"Processing collection image file: {filename}")

    clean_name = clean_name_for_folder(os.path.splitext(filename)[0])
    matched_collection = find_collection_match(clean_name, language_data)

    if matched_collection:
        # Use the extracted title from the match
        extracted_title = matched_collection['extracted_title']
        folder_name = sanitize_folder_name(extracted_title)

        new_folder = os.path.join(COLLECTIONS_DIR, folder_name)
        os.makedirs(new_folder, exist_ok=True)

        new_filename = "poster.jpg"
        new_file_path = os.path.join(new_folder, new_filename)

        # Archive existing content if necessary
        if os.path.exists(new_file_path):
            archive_existing_content(Path(new_folder))

        # Move the file to the new folder and rename it
        shutil.move(file_path, new_file_path)
        logger.info(f"Collection file moved and renamed to: {new_file_path}")

        return new_file_path
    else:
        logger.warning(f"No match found for collection: {filename}")
        # Pass is_collection=True to ensure it goes to the Collections subfolder
        return process_unmatched_file(file_path, clean_name, year=None, is_collection=True)


def process_unmatched_file(file_path, clean_name, year=None, is_collection=False):
    """Process an unmatched file by moving it to the appropriate NO_MATCH_FOLDER subfolder."""
    folder_name = f"{clean_name} ({year})" if year else clean_name

    # Choose the appropriate subfolder based on whether it's a collection
    subfolder = 'Collections' if is_collection else 'Poster'
    no_match_folder = os.path.join(NO_MATCH_FOLDER, subfolder, folder_name)
    os.makedirs(no_match_folder, exist_ok=True)

    new_file_path = os.path.join(no_match_folder, os.path.basename(file_path))
    shutil.move(file_path, new_file_path)

    logger.info(f"Unmatched {'collection' if is_collection else 'file'} moved to: {new_file_path}")
    return new_file_path


def clean_name(filename):
    """Clean the filename by removing season, episode, and specials information, but preserving the year."""
    logger.debug(f"Cleaning name for: {filename}")
    name = os.path.splitext(filename)[0]
    name = re.sub(r'\s*-\s*S\d+\s*E\d+', '', name)
    name = re.sub(r'\s*-\s*Season\s*\d+', '', name)
    name = re.sub(r'\s*-\s*Specials', '', name)
    name = re.sub(r'\s*-\s*Backdrop', '', name)
    name = re.sub(r'\s*-\s*Background', '', name)
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
    name_ratio = fuzz.ratio(clean_name.lower(), item_name.lower())

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
    return bool(re.search(r'collection|filmreihe', filename.lower()))


def process_image_file(file_path, language_data):
    """Process an individual image file."""
    filename = os.path.basename(file_path)
    logger.info(f"Processing image file: {filename}")

    # Convert the image to JPG format
    file_path = convert_to_jpg(file_path)
    filename = os.path.basename(file_path)

    # First check if it's a collection
    if is_collection(filename):
        logger.info(f"Detected collection file: {filename}")
        return process_collection(file_path, language_data)

    # If not a collection, continue with regular processing...
    is_background = any(term in filename.lower() for term in ['backdrop', 'background'])
    clean_name_result = clean_name(filename)
    year_match = re.search(r'\((\d{4})\)', filename)
    year = year_match.group(1) if year_match else None

    matched_item = find_match(clean_name_result, language_data)

    if matched_item:
        # Rest of the existing regular processing code...
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
        logger.warning(f"No match found for: {filename}")
        series_name, file_year = get_series_name(filename)
        year_to_use = year or file_year
        timestamp = get_timestamp_folder()
        folder_name = f"{series_name} ({year_to_use})" if year_to_use else series_name
        no_match_folder = Path(NO_MATCH_FOLDER) / 'Poster' / folder_name / timestamp
        no_match_folder.mkdir(parents=True, exist_ok=True)

        new_file_path = no_match_folder / filename
        shutil.move(file_path, new_file_path)

        logger.info(f"File {filename} moved to No-Match Poster subfolder: {new_file_path}")
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
    """Move file to Consumed folder, handling existing files."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found, skipping move to Consumed: {file_path}")
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
        logger.info(f"File moved to Consumed folder: {consumed_file_path}")
        return True
    except Exception as e:
        logger.error(f"Error moving file to Consumed folder: {str(e)}")
        return False


def archive_existing_content(target_dir: Path):
    if not any(target_dir.iterdir()):  # Check if the directory is empty
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dir_name = target_dir.name

    # Determine if it's a collection or a regular poster
    is_collection = 'collection' in dir_name.lower() or 'filmreihe' in dir_name.lower()
    replaced_subdir = 'Collections' if is_collection else 'Poster'

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

def cover_cleaner():
    global LAST_TIMESTAMP
    LAST_TIMESTAMP = None

    # Load language data
    language_data = load_language_data()

    folder_matcher = FolderMatcher(language_data)

    files = os.listdir(RAW_COVER_DIR)

    if files:  # Check if there are any files
        for filename in files:
            file_path = os.path.join(RAW_COVER_DIR, filename)
            logger.info(f"Processing file: {filename}")

            try:
                if filename.endswith('.zip'):
                    process_zip_file(file_path, language_data)
                elif filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    original_file_path = file_path
                    destination_path = os.path.join(CONSUMED_DIR, os.path.basename(original_file_path))

                    shutil.copy(original_file_path, destination_path)
                    logger.info(f"File copied to {destination_path}")

                    if process_image_file(file_path, language_data):
                        # Check if the file was moved during processing
                        if not os.path.exists(file_path):
                            logger.info(f"File was moved during processing: {filename}")
                        else:
                            move_to_consumed(file_path)
                    else:
                        logger.warning(f"Failed to process image file: {filename}")
            except Exception as e:
                logger.error(f"Error processing {filename}: {str(e)}")
                # Try to move the original file if it still exists
                if os.path.exists(original_file_path):
                    move_to_consumed(original_file_path)

        # Refresh the directory lookup after processing all files
        updater.scan_directories()
        logger.info("Directory lookup refreshed after processing files")
        folder_matcher.reprocess_unmatched_files()
    else:
        logger.info('No files found in the folder.')


if __name__ == "__main__":
    cover_cleaner()
