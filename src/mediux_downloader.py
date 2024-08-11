#Full Credit to nea89o https://github.com/nea89o

import json
import re
import sys
import zipfile
from PIL import Image
import io
import requests

from src.utils import log
from src.constants import RAW_COVER_DIR
from src.updateCover import clean_name
from src.CoverCleaner import organize_covers

extension = 'jpg'
format = 'JPEG'


def mediux_downloader():
    with (open('mediux.txt', 'r') as file):
        for download_url in map(str.strip,file):
            if not download_url.startswith("https://mediux.pro/sets"):
                log("Please select a set link instead of a collection link.")
                sys.exit(1)

            log('Downloading set information')
            html = download_set_html(download_url)
            log('Extracting set information')
            data = extract_json_segment(html)
            set_data = data['set']
            set_name = "Unknown Collection"
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
            files = set_data['files']
            log(f'Saving all set images to {set_name}.zip')
            with zipfile.ZipFile(RAW_COVER_DIR / (set_name + ".zip"), 'w') as zf:
                download_images(files, zf)
            print("All images downloaded! This script is now finished!")
            organize_covers()



def download_images(file_collection, zf: zipfile.ZipFile):
    for file in file_collection:
        file_url = 'https://api.mediux.pro/assets/' + file["id"]
        file_title = file['title'].strip()
        file_title = clean_name(file_title)

        file_name = file_title + "." + extension


        print(f'Downloading {file_title} from {file_url}')
        source_bytes = requests.get(file_url).content
        img = Image.open(io.BytesIO(source_bytes))
        if img.format != format:
            img = img.convert('RGB')
        with zf.open(file_name, 'w') as fp:
            img.save(fp, format)


def download_set_html(url):
    data = requests.get(url).text
    return data


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


if __name__ == '__main__':
    mediux_downloader()
