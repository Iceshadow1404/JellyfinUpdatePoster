#Full Credit to nea89o https://github.com/nea89o

import json
import re
import sys
import zipfile
from PIL import Image
import io
import requests
import asyncio
import aiohttp
from aiohttp import ClientSession
from collections import defaultdict
import os
import warnings
import os

from src.utils import log
from src.constants import RAW_COVER_DIR, MEDIUX_FILE
from src.updateCover import clean_name

extension = 'jpg'
format = 'JPEG'


def mediux_downloader():
    asyncio.run(async_mediux_downloader())


async def async_mediux_downloader():
    downloaded_files = defaultdict(list)
    with open(MEDIUX_FILE, 'r') as file:
        download_urls = list(map(str.strip, file))

    for index, download_url in enumerate(download_urls):
        if not download_url.startswith("https://mediux.pro/sets"):
            log("Please select a set link instead of a collection link.")
            print("Invialid Link:", download_url)
            sys.exit(1)

        log(f'Downloading set information for URL {index + 1}')
        html = await download_set_html(download_url)
        log('Extracting set information')
        data = extract_json_segment(html)
        set_data = data['set']
        set_name = get_set_name(set_data)
        series_name = get_series_name(set_name)
        set_name = clean_name(set_name)
        files = set_data['files']
        zip_filename = f"{set_name}_{index + 1}.zip"
        log(f'Saving all set images to {zip_filename}')
        with zipfile.ZipFile(RAW_COVER_DIR / zip_filename, 'w') as zf:
            await download_images(files, zf)
        downloaded_files[series_name].append(zip_filename)
        log(f"All images downloaded for URL {index + 1}!")

    for series_name, zip_files in downloaded_files.items():
        if len(zip_files) > 1:
            merge_zip_files(zip_files, series_name)
        else:
            log(f"Only one ZIP file for {series_name}, no merging needed.")
    with open(MEDIUX_FILE, 'w') as file:
        log("Reset mediux.txt")


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


def merge_zip_files(zip_files, series_name):
    base_zip = zip_files[0]
    output_zip = f"{series_name}_merged.zip"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(RAW_COVER_DIR / output_zip, 'w') as zf_out:
            for zip_file in zip_files:
                with zipfile.ZipFile(RAW_COVER_DIR / zip_file, 'r') as zf_in:
                    for item in zf_in.infolist():
                        buffer = zf_in.read(item.filename)
                        zf_out.writestr(item, buffer)

    log(f"Merged ZIP file created for {series_name}: {output_zip}")

    # Löschen der ursprünglichen ZIP-Dateien
    for zip_file in zip_files:
        os.remove(RAW_COVER_DIR / zip_file)
    log(f"Original ZIP files for {series_name} removed.")

async def download_images(file_collection, zf: zipfile.ZipFile):
    async with ClientSession() as session:
        tasks = []
        for file in file_collection:
            file_url = 'https://api.mediux.pro/assets/' + file["id"]
            file_title = file['title'].strip()
            file_title = clean_name(file_title)
            file_name = file_title + "." + extension

            log(f'Queuing download for {file_title} from {file_url}')
            task = asyncio.create_task(download_and_save_image(session, file_url, file_name, zf))
            tasks.append(task)

        await asyncio.gather(*tasks)


async def download_set_html(url):
    async with ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

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

async def download_and_save_image(session: ClientSession, file_url: str, file_name: str, zf: zipfile.ZipFile):
    async with session.get(file_url) as response:
        if response.status == 200:
            source_bytes = await response.read()
            img = Image.open(io.BytesIO(source_bytes))
            if img.format != format:
                img = img.convert('RGB')
            with zf.open(file_name, 'w') as fp:
                img.save(fp, format)
            log(f'Downloaded and saved {file_name}')
        else:
            log(f'Failed to download {file_name}. Status code: {response.status}',success=False)

if __name__ == '__main__':
    mediux_downloader()