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

from src.config import JELLYFIN_URL, API_KEY
from src.updateCover import UpdateCover
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

    best_match = None
    best_score = 0

    for item_id, item_data in language_data.items():
        if item_id == 'last_updated':
            continue

        if item_data.get('Type', '').lower() == 'boxset' or item_data.get('type', '').lower() == 'boxset':
            collection_name = item_data.get('Name', '')
            collection_year = item_data.get('Year') or item_data.get('year')
            tmdb_id = item_data.get('TMDbId') or item_id  # Use TMDbId or item_id as fallback
            extracted_title = item_data.get('extracted_title', collection_name)

            # Compare with the main collection name
            score = fuzz.ratio(clean_name.lower(), collection_name.lower())

            # Compare with additional titles if available
            if 'titles' in item_data:
                for title in item_data['titles']:
                    title_score = fuzz.ratio(clean_name.lower(), title.lower())
                    score = max(score, title_score)

            # Additional comparison with 'Collection' appended if it's not already there
            if 'collection' not in clean_name.lower():
                collection_score = fuzz.ratio(f"{clean_name} Collection".lower(), collection_name.lower())
                score = max(score, collection_score)

            if score > best_score:
                best_score = score
                best_match = {
                    'id': item_id,
                    'name': collection_name,
                    'year': collection_year,
                    'tmdb_id': tmdb_id,
                    'extracted_title': extracted_title
                }

    if best_score >= 90:  # Threshold for a lenient match
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
        extracted_title = matched_collection['extracted_title']
        folder_name = sanitize_folder_name(extracted_title)

        new_folder = os.path.join(COLLECTIONS_DIR, folder_name)
        os.makedirs(new_folder, exist_ok=True)

        new_filename = "poster.jpg"
        new_file_path = os.path.join(new_folder, new_filename)

        # If a file with the same name already exists, archive the existing content
        if os.path.exists(new_file_path):
            archive_existing_content(Path(new_folder))


        # Move the file to the new folder and rename it
        shutil.move(file_path, new_file_path)
        logger.info(f"Collection file moved and renamed to: {new_file_path}")

        return new_file_path
    else:
        logger.warning(f"No match found for collection: {filename}")
        return process_unmatched_file(file_path, clean_name)

def process_unmatched_file(file_path, clean_name):
    """Process an unmatched file by moving it to the NO_MATCH_FOLDER."""
    no_match_folder = os.path.join(NO_MATCH_FOLDER, clean_name)
    os.makedirs(no_match_folder, exist_ok=True)

    new_file_path = os.path.join(no_match_folder, os.path.basename(file_path))
    shutil.move(file_path, new_file_path)

    logger.info(f"Unmatched file moved to: {new_file_path}")
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
    """Extract the series name from the filename."""
    # Remove season and episode information
    name = re.sub(r'\s*-\s*S\d+\s*E\d+', '', filename)
    name = re.sub(r'\s*-\s*Season\s*\d+', '', name)
    # Remove any mention of 'Specials'
    name = re.sub(r'\s*-\s*Specials', '', name, flags=re.IGNORECASE)
    # Remove year if present
    name = re.sub(r'\s*\(\d{4}\)', '', name)
    # Remove any mention of 'backdrop' or 'background'
    name = re.sub(r'\s*-?\s*(Backdrop|Background)', '', name, flags=re.IGNORECASE)
    # Remove file extension
    name = os.path.splitext(name)[0]
    return clean_name_for_folder(name)

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

    for item_id, item_data in language_data.items():
        if item_id == 'last_updated':
            continue

        extracted_title = item_data.get('extracted_title', '')
        original_title = item_data.get('originaltitle', '')
        item_year = item_data.get('year')

        # Compare with extracted_title
        extracted_title_score = compare_titles(clean_name_without_year, extracted_title, item_year, file_year)

        # Compare with original_title
        original_title_score = compare_titles(clean_name_without_year, original_title, item_year,
                                              file_year) if original_title else 0

        # Compare with all titles in the array
        title_scores = [compare_titles(clean_name_without_year, title, item_year, file_year) for title in
                        item_data.get('titles', [])]

        # Get the maximum score from all comparisons
        max_score = max([extracted_title_score, original_title_score] + title_scores)

        if max_score > best_score:
            best_score = max_score
            best_match = {
                'id': item_id,
                'extracted_title': extracted_title,
                'original_title': original_title,
                'year': item_year
            }

        logger.debug(
            f"Comparing with - Extracted Title: {extracted_title} ({extracted_title_score}), Original Title: {original_title} ({original_title_score}), Max Title Score: {max(title_scores) if title_scores else 0}, Year: {item_year}")

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
    return 'collection' in filename.lower() or 'filmreihe' in filename.lower()

def process_image_file(file_path, language_data):
    """Process an individual image file."""
    filename = os.path.basename(file_path)
    logger.info(f"Processing image file: {filename}")

    # Convert the image to JPG format
    file_path = convert_to_jpg(file_path)
    filename = os.path.basename(file_path)

    # Determine if it's a collection before cleaning the name
    collection_flag = is_collection(filename)

    clean_name_result = clean_name(filename)
    matched_item = find_match(clean_name_result, language_data)

    if matched_item:
        extracted_title = matched_item['extracted_title']
        original_title = matched_item.get('original_title', '')
        year = matched_item.get('year', '')

        display_title = (
            original_title if original_title and original_title != extracted_title and not contains_non_ascii(original_title)
            else extracted_title
        )

        folder_name = f"{display_title} ({year})" if year and not collection_flag else display_title
        folder_name = sanitize_folder_name(folder_name)

        # Use the collection_flag to determine the correct folder
        new_folder = os.path.join(COLLECTIONS_DIR if collection_flag else POSTER_DIR, folder_name)
        os.makedirs(new_folder, exist_ok=True)

        if re.search(r'S\d+\s*E\d+', filename):
            # Process episode image
            season_episode = re.search(r'S(\d+)\s*E(\d+)', filename)
            new_filename = f"S{int(season_episode.group(1)):02d}E{int(season_episode.group(2)):02d}.jpg"
        elif 'Season' in filename:
            # Process season poster
            season_number = re.search(r'Season\s*(\d+)', filename)
            new_filename = f"Season{int(season_number.group(1)):02d}.jpg"
        elif 'Specials' in filename:
            new_filename = "Season00.jpg"
        elif 'Backdrop' in filename:
            new_filename = "background.jpg"
        else:
            # Assume it's a series/movie poster
            new_filename = "poster.jpg"

        new_file_path = os.path.join(new_folder, new_filename)

        # Archive existing content if file already exists
        if os.path.exists(new_file_path):
            archive_existing_content(Path(new_folder))

        shutil.move(file_path, new_file_path)
        return True  # Indicate that the file was processed and moved
    else:
        # No match found: create a subfolder structure
        logger.warning(f"No match found for: {filename}")
        series_name = get_series_name(filename)  # Get a consistent series name

        # Use the collection_flag to determine the correct subfolder
        subfolder = 'Collections' if collection_flag else 'Poster'

        # Get the timestamp folder name
        timestamp = get_timestamp_folder()

        # Create the folder structure: NO_MATCH_FOLDER / subfolder / series_name / timestamp
        no_match_folder = Path(NO_MATCH_FOLDER) / subfolder / series_name / timestamp
        no_match_folder.mkdir(parents=True, exist_ok=True)

        new_file_path = no_match_folder / filename
        shutil.move(file_path, new_file_path)

        logger.info(f"File {filename} moved to No-Match {subfolder} subfolder: {new_file_path}")
        return True

    return False  # If we reach here, something went wrong

def contains_non_ascii(s):
    return any(ord(char) > 127 for char in s)


def process_zip_file(zip_path, language_data):
    """Process a ZIP file containing multiple image files."""
    logger.info(f"Processing ZIP file: {zip_path}")
    temp_dir = os.path.join(RAW_COVER_DIR, 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    extract_zip(zip_path, temp_dir)

    processed_files = []
    for extracted_file in os.listdir(temp_dir):
        extracted_file_path = os.path.join(temp_dir, extracted_file)
        if extracted_file.lower().endswith(('.jpg', '.jpeg', '.png')):
            converted_file_path = convert_to_jpg(extracted_file_path)
            if process_image_file(converted_file_path, language_data):
                processed_files.append(extracted_file)

    shutil.rmtree(temp_dir)

    # Move the processed ZIP file to the CONSUMED_DIR
    move_to_consumed(zip_path)

    return True  # Indicate that the ZIP file was processed


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

def find_matching_folder(folder_name, language_data):
    """Find a matching item in language data for the given folder name."""
    clean_folder_name = clean_name(folder_name.lower())
    for item in language_data.values():
        if 'extracted_title' in item:
            clean_item_name = clean_name(item['extracted_title'].lower())
            if fuzz.ratio(clean_folder_name, clean_item_name) >= 90:
                return True
    return False



def reprocess_unmatched_files(language_data):
    """Reprocess unmatched files after new content is added."""
    logger.info("Reprocessing unmatched files")

    for subfolder in ['Collections', 'Poster']:
        no_match_path = Path(NO_MATCH_FOLDER) / subfolder
        if not no_match_path.exists():
            continue

        for series_folder in no_match_path.iterdir():
            if not series_folder.is_dir():
                continue

            # Check if the folder name matches any item in language_data
            if not find_matching_folder(series_folder.name, language_data):
                logger.info(f"No match found for {series_folder.name}, skipping.")
                continue

            logger.info(f"Match found for {series_folder.name}, processing...")

            # Find the newest dated subfolder
            dated_subfolders = [f for f in series_folder.iterdir() if f.is_dir()]
            if not dated_subfolders:
                continue

            newest_subfolder = max(dated_subfolders, key=lambda x: x.stat().st_mtime)

            # Create a zip file in RAW_COVER_DIR
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"{series_folder.name}_{timestamp}.zip"
            zip_path = RAW_COVER_DIR / zip_filename

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in newest_subfolder.iterdir():
                    if file.is_file():
                        zipf.write(file, file.name)
                        logger.info(f"Added {file.name} to {zip_filename}")

            logger.info(f"Created zip file: {zip_filename}")

            # Remove the files from the newest subfolder
            for file in newest_subfolder.iterdir():
                if file.is_file():
                    file.unlink()
                    logger.info(f"Removed file: {file}")

            # Remove the empty subfolder
            if not any(newest_subfolder.iterdir()):
                newest_subfolder.rmdir()
                logger.info(f"Removed empty subfolder: {newest_subfolder}")

            # Remove the series folder if it's empty
            if not any(series_folder.iterdir()):
                series_folder.rmdir()
                logger.info(f"Removed empty series folder: {series_folder}")

    logger.info("Finished reprocessing unmatched files")


def cover_cleaner():
    global LAST_TIMESTAMP
    LAST_TIMESTAMP = None
    """Main function to process all files in the RAW_COVER_FOLDER."""
    # Load language data
    language_data = load_language_data()

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
    else:
        logger.info('No files found in the folder.')

    # Reprocess unmatched files
    reprocess_unmatched_files(language_data)


if __name__ == "__main__":
    cover_cleaner()
