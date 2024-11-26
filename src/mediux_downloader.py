import json
import re
import sys
import zipfile
from PIL import Image
import io
import requests
from collections import defaultdict
import warnings
import os

from src.logging import logging
from src.constants import RAW_COVER_DIR, MEDIUX_FILE
from src.coverCleaner import clean_name

logger = logging.getLogger(__name__)


def mediux_downloader():
    downloaded_files = defaultdict(list)
    source_data = {}  # Store additional information about each source

    with open(MEDIUX_FILE, 'r') as file:
        download_urls = list(map(str.strip, file))

    for index, download_url in enumerate(download_urls):
        if not download_url.startswith("https://mediux.pro/sets"):
            logging.info("Please select a set link instead of a collection link.")
            print("Invalid Link:", download_url)
            sys.exit(1)

        logging.info(f'Downloading set information for URL {index + 1}')
        html = download_set_html(download_url)
        logging.info('Extracting set information')
        data = extract_json_segment(html)
        set_data = data['set']
        set_name = get_set_name(set_data)
        set_name = clean_name(set_name)
        series_name = get_series_name(set_name)
        files = set_data['files']
        zip_filename = f"{set_name}_{index + 1}.zip"
        logging.info(f'Saving all set images to {zip_filename}')

        with zipfile.ZipFile(RAW_COVER_DIR / zip_filename, 'w') as zf:
            downloaded_files = download_images(files, zf, set_name, downloaded_files)

        # Save additional information
        source_data[zip_filename] = {
            'series_name': series_name,
            'files': files,
            'source_url': download_url
        }

        logging.info(f"All images downloaded for URL {index + 1}!")

    # Smart merge strategy
    smart_merge_files(source_data)

    with open(MEDIUX_FILE, 'w') as file:
        pass

def get_set_name(set_data):
    if set_data.get('show'):
        set_name = set_data['show']['name']
        try:
            set_name += f' ({set_data["show"]["first_air_data"][:4]})'
        except:
            pass
    elif set_data.get('collection'):
        set_name = set_data["collection"]["collection_name"]
    elif set_data.get('set_name'):
        set_name = set_data['set_name']
    else:
        set_name = "Unknown Collection"
    return set_name

def get_series_name(set_name):
    return re.sub(r'\s*\(\d{4}\)$', '', set_name)


def smart_merge_files(source_data):
    # Group by series
    series_sources = defaultdict(list)
    for zip_file, data in source_data.items():
        series_sources[data['series_name']].append({
            'zip_file': zip_file,
            'files': data['files']
        })

    # For each series
    for series_name, sources in series_sources.items():
        if len(sources) > 1:
            # Sort sources by number of files (descending)
            sources.sort(key=lambda x: len(x['files']), reverse=True)

            # Merge strategy
            merged_files = {}
            for source in sources:
                for file in source['files']:
                    # Generate episode key
                    if file.get('fileType') == 'episode':
                        key = (
                            file.get('season', 'Unknown'),
                            file.get('number', 'Unknown')
                        )

                        # Add only if not present or new source is more detailed
                        if key not in merged_files or len(str(file.get('id', ''))) > len(
                                str(merged_files[key].get('id', ''))):
                            merged_files[key] = file

            # Create new zip with merged files
            output_zip_name = f"{series_name}_merged.zip"
            with zipfile.ZipFile(RAW_COVER_DIR / output_zip_name, 'w') as zf_out:
                for source in sources:
                    with zipfile.ZipFile(RAW_COVER_DIR / source['zip_file'], 'r') as zf_in:
                        for file in zf_in.infolist():
                            # Keep only files not replaced by better source
                            buffer = zf_in.read(file.filename)
                            zf_out.writestr(file, buffer)

            # Delete old zip files
            for source in sources:
                os.remove(RAW_COVER_DIR / source['zip_file'])

            logging.info(f"Smart merged ZIP created for {series_name}: {output_zip_name}")


def download_images(file_collection, zf: zipfile.ZipFile, set_name: str, downloaded_files=None):
    if downloaded_files is None:
        downloaded_files = defaultdict(list)

    for file in file_collection:
        # Extended logic for filenames and types
        if file.get('fileType') == 'backdrop':
            file_title = f"{set_name} - Background"
        elif file.get('fileType') == 'episode':
            # For episode covers
            episode_name = file.get('title', 'Unknown Episode')
            season_number = file.get('season', 'Unknown Season')
            episode_number = file.get('number', 'Unknown')
            file_title = f"{set_name} - S{season_number}E{episode_number} - {episode_name}"
        else:
            # Fallback for other file types
            file_title = file.get('title', 'Unnamed').strip()

        file_name = file_title + ".jpg"
        file_url = 'https://api.mediux.pro/assets/' + file["id"]

        logging.info(f'Downloading {file_title} from {file_url}')
        download_and_save_image(file_url, file_name, zf)

    return downloaded_files

def download_set_html(url):
    response = requests.get(url)
    return response.text

def is_data_chunk(chunk):
    return "set_description" in chunk or "original_name" in chunk

def extract_json_from_chunk(chunk_text: str):
    string_begin = chunk_text.find('"')
    string_end = chunk_text.rfind('"')
    outer_json: str = json.loads(chunk_text[string_begin:string_end + 1])
    return json.loads(outer_json[outer_json.find(':') + 1:])[3]

def extract_json_segment(text):
    push_regex = re.compile('<script>self.__next_f.push(.*?)</script>')
    pushes = [chunk for chunk in
              map(lambda match: match[1],
                  re.finditer(push_regex, text)) if is_data_chunk(chunk)]
    json_chunks = [extract_json_from_chunk(chunk) for chunk in pushes]
    return json_chunks[0]

def download_and_save_image(file_url: str, file_name: str, zf: zipfile.ZipFile):
    try:
        response = requests.get(file_url)
        if response.status_code == 200:
            source_bytes = response.content
            img = Image.open(io.BytesIO(source_bytes))
            if img.format != 'JPEG':
                img = img.convert('RGB')
            with zf.open(file_name, 'w') as fp:
                img.save(fp, 'JPEG')
            logging.info(f'Downloaded and saved {file_name}')
        else:
            logging.info(f'Failed to download {file_name}. Status code: {response.status_code}', success=False)
    except Exception as e:
        logging.info(f'Error downloading {file_name}: {str(e)}', success=False)

if __name__ == '__main__':
    mediux_downloader()