import os
import zipfile
import re
import shutil
from dotenv import load_dotenv
import requests
from fuzzywuzzy import fuzz
import logging
from PIL import Image
from datetime import datetime
from pathlib import Path

from src.config import *
from src.constants import POSTER_DIR, COLLECTIONS_DIR, OUTPUT_FILENAME, MISSING, EXTRA_FOLDER, RAW_COVER_DIR, NO_MATCH_FOLDER, CONSUMED_DIR
from src.updateCover import directory_manager

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
            logging.error(f"Error converting {file_path} to JPG: {str(e)}")
            return file_path
    elif file_extension.lower() == '.jpeg':
        new_file_path = f"{filename}.jpg"
        os.rename(file_path, new_file_path)
        return new_file_path
    return file_path

def process_collection(file_path):
    """Process a collection image file."""
    filename = os.path.basename(file_path)
    logging.info(f"Processing collection image file: {filename}")

    folder_name = os.path.splitext(filename)[0].replace(' Collection', '')

    # Create a new folder inside the 'Collections' folder with the name derived from the file
    new_folder = os.path.join(COLLECTIONS_DIR, folder_name)
    os.makedirs(new_folder, exist_ok=True)

    new_filename = 'poster.png'
    new_file_path = os.path.join(new_folder, new_filename)

    # If a file with the same name already exists, add a number to the filename
    counter = 1
    while os.path.exists(new_file_path):
        new_filename = f'poster_{counter}.png'
        new_file_path = os.path.join(new_folder, new_filename)
        counter += 1

    # Move the file to the new folder and rename it to poster.png
    shutil.move(file_path, new_file_path)
    logging.info(f"Collection file moved and renamed to: {new_file_path}")


def clean_name(filename):
    """Clean the filename by removing season, episode, and specials information, but preserving the year."""
    logging.debug(f"Cleaning name for: {filename}")
    name = os.path.splitext(filename)[0]
    name = re.sub(r'\s*-\s*S\d+\s*E\d+', '', name)
    name = re.sub(r'\s*-\s*Season\s*\d+', '', name)
    name = re.sub(r'\s*-\s*Specials', '', name)
    name = re.sub(r'\s*-\s*Backdrop', '', name)
    name = re.sub(r'\s*-\s*Background', '', name)
    cleaned_name = name.strip()
    logging.debug(f"Cleaned name: {cleaned_name}")
    return cleaned_name

def clean_name_for_folder(name):
    """Remove years, parentheses, and other unwanted characters from the name."""
    cleaned = re.sub(r'\s*\(\d{4}\)', '', name)  # Remove year in parentheses
    cleaned = re.sub(r'\(.*?\)', '', cleaned)  # Remove any remaining parentheses and their contents
    cleaned = re.sub(r'[^\w\-_\. ]', '', cleaned)  # Remove any non-alphanumeric characters except dash, underscore, dot, and space
    return cleaned.strip()

def extract_zip(zip_path, extract_to):
    """Extract contents of a ZIP file."""
    logging.info(f"Extracting ZIP file: {zip_path}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    logging.info(f"ZIP file extracted to: {extract_to}")


def get_jellyfin_items():
    """Retrieve Jellyfin items from API or cache."""
    logging.info("Retrieving Jellyfin items from API")
    url = f"{JELLYFIN_URL}/Items"
    params = {
        'api_key': API_KEY,
        'Recursive': 'true',
        'IncludeItemTypes': 'Series,Movie',
        'Fields': 'Name,OriginalTitle,Id,ParentId,ParentIndexNumber,Seasons,IndexNumber,ProductionYear'
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        items = response.json()['Items']
        logging.info(f"{len(items)} Jellyfin items retrieved")
        return items
    else:
        logging.error(f"Error retrieving Jellyfin items: {response.status_code}")
        return []


def find_match(clean_name, jellyfin_items):
    """Find a matching item in Jellyfin items, considering the year if available."""
    logging.debug(f"Searching for match: {clean_name}")

    # Extract year from clean_name if present
    year_match = re.search(r'\((\d{4})\)', clean_name)
    file_year = int(year_match.group(1)) if year_match else None
    clean_name_without_year = re.sub(r'\s*\(\d{4}\)', '', clean_name).strip()

    best_match = None
    best_score = 0

    for item in jellyfin_items:
        title = item.get('Name', '')
        original_title = item.get('OriginalTitle', '')
        item_year = item.get('ProductionYear')

        title_score = compare_titles(clean_name_without_year, title, item_year, file_year)
        original_title_score = compare_titles(clean_name_without_year, original_title, item_year, file_year)

        max_score = max(title_score, original_title_score)

        if max_score > best_score:
            best_score = max_score
            best_match = item

        logging.debug(
            f"Comparing with - Title: {title} ({title_score}), Original Title: {original_title} ({original_title_score}), Year: {item_year}")

    if best_score >= 90:
        logging.info(f"Match found: {best_match['Name']} ({best_score})")
        return best_match

    logging.warning(f"No match found for: {clean_name}")
    return None


def compare_titles(clean_name, item_name, item_year, file_year):
    """Compare titles considering the year if available."""
    name_ratio = fuzz.ratio(clean_name, item_name)

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


def process_image_file(file_path, jellyfin_items):
    """Process an individual image file."""
    filename = os.path.basename(file_path)
    logging.info(f"Processing image file: {filename}")

    # Convert the image to JPG format
    file_path = convert_to_jpg(file_path)
    filename = os.path.basename(file_path)

    if 'Collection' in filename:
        process_collection(file_path)
        return

    clean_name_result = clean_name(filename)
    matched_item = find_match(clean_name_result, jellyfin_items)

    if matched_item:
        series_name = matched_item['Name']
        year = matched_item.get('ProductionYear', '')
        folder_name = f"{series_name} ({year})" if year else series_name
        folder_name = sanitize_folder_name(folder_name)

        new_folder = os.path.join(POSTER_DIR, folder_name)
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
        logging.info(f"File moved and renamed to: {new_file_path}")
        return True  # Indicate that the file was processed and moved
    else:
        # No match found: add to existing ZIP or create a new one
        logging.warning(f"No match found for: {filename}")
        clean_name_result = clean_name_for_folder(clean_name_result)
        no_match_folder = os.path.join(NO_MATCH_FOLDER, clean_name_result)
        os.makedirs(no_match_folder, exist_ok=True)

        zip_filename = os.path.join(no_match_folder, f"{clean_name_result}.zip")

        # Open the existing ZIP file or create a new one and append the current image
        with zipfile.ZipFile(zip_filename, 'a') as zipf:
            zipf.write(file_path, arcname=filename)

        logging.info(f"File {filename} added to No-Match ZIP: {zip_filename}")
        os.remove(file_path)  # Remove the original file after adding to the ZIP
        return True  # Indicate that the file was processed and moved



def process_zip_file(zip_path, jellyfin_items):
    """Process a ZIP file containing multiple image files."""
    logging.info(f"Processing ZIP file: {zip_path}")
    temp_dir = os.path.join(RAW_COVER_DIR, 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    extract_zip(zip_path, temp_dir)

    for extracted_file in os.listdir(temp_dir):
        extracted_file_path = os.path.join(temp_dir, extracted_file)
        if extracted_file.lower().endswith(('.jpg', '.jpeg', '.png')):
            converted_file_path = convert_to_jpg(extracted_file_path)
            process_image_file(converted_file_path, jellyfin_items)

    shutil.rmtree(temp_dir)

    # Return True to indicate successful processing
    return True


def move_to_consumed(file_path):
    """Move file to Consumed folder, handling existing files."""
    if not os.path.exists(file_path):
        logging.warning(f"File not found, skipping move to Consumed: {file_path}")
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
        logging.info(f"File moved to Consumed folder: {consumed_file_path}")
        return True
    except Exception as e:
        logging.error(f"Error moving file to Consumed folder: {str(e)}")
        return False

def archive_existing_content(target_dir: Path):
    if not any(target_dir.iterdir()):  # Check if the directory is empty
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dir_name = target_dir.name
    zip_filename = f"{dir_name}_{timestamp}.zip"
    replaced_dir = Path(CONSUMED_DIR) / dir_name
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

    logging.info(f"Archived existing content: {zip_path}")

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

def cover_cleaner():
    """Main function to process all files in the RAW_COVER_FOLDER."""
    files = os.listdir(RAW_COVER_DIR)

    if files:  # Check if there are any files
        jellyfin_items = get_jellyfin_items()
        for filename in files:
            file_path = os.path.join(RAW_COVER_DIR, filename)
            logging.info(f"Processing file: {filename}")

            try:
                if filename.endswith('.zip'):
                    if process_zip_file(file_path, jellyfin_items):
                        move_to_consumed(file_path)
                elif filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    if not process_image_file(file_path, jellyfin_items):
                        move_to_consumed(file_path)
            except Exception as e:
                logging.error(f"Error processing {filename}: {str(e)}")
                move_to_consumed(file_path)
    else:
        logging.info('No files found in the folder.')

    directory_manager.scan_directories()
if __name__ == "__main__":
    cover_cleaner()