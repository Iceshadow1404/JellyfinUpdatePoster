import json
import requests
import re
import os
from updateCover import clean_json_names, assign_images_and_update_jellyfin, missing_folders

with open("config.json", 'r') as file:
    data = json.load(file)

jellyfin_url = data["jellyfin_url"]
api_key = data["api_key"]

output_filename = 'sorted_series.json'
raw_filename = 'raw.json'

def start_get_and_save_series_and_movie(api_key, jellyfin_url):
    media_list = get_and_save_series_and_movies(api_key, jellyfin_url)
    if media_list:
        new_sorted_data = sort_series_and_movies(raw_filename)
        if new_sorted_data:
            save_if_different(output_filename, new_sorted_data)
        else:
            print("Failed to sort series and movies data.")
    else:
        print("Failed to retrieve series and movies data.")

def get_and_save_series_and_movies(api_key, jellyfin_url):
    headers = {
        'X-Emby-Token': api_key
    }
    url = f'{jellyfin_url}/Items'
    params = {
        'Recursive': 'true',
        'IncludeItemTypes': 'Series,Season,Movie,BoxSet',
        'Fields': 'Name,OriginalTitle,Id,ParentId,ParentIndexNumber,Seasons,ProductionYear'  # Add OriginalTitle
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Request failed with status code {response.status_code}")
        return None

    items = response.json().get('Items')
    if not items:
        print("No items found in the response")
        return None

    media_list = []
    for item in items:
        media_info = {
            'Id': item['Id'],
            'Name': item.get('Name'),
            'ParentId': item.get('ParentId'),
            'Type': item['Type'],
            'Year': item.get('ProductionYear', 'Unknown')
        }
        if 'OriginalTitle' in item:
            media_info['OriginalTitle'] = item['OriginalTitle']

        media_info['Name'] = clean_movie_name(media_info['Name'])

        media_list.append(media_info)

    with open(raw_filename, 'w', encoding='utf-8') as f:
        json.dump(media_list, f, ensure_ascii=False, indent=4)
    return media_list

def clean_movie_name(name):
    pattern = r' \(\d{4}\)$'
    return re.sub(pattern, '', name)

def sort_series_and_movies(input_filename):
    try:
        with open(input_filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return None

    series_dict = {}
    specials_dict = {}
    boxsets = []

    for item in data:
        if item['Type'] == 'BoxSet':
            boxsets.append(item)
            continue

        if item['Name'] == "Season Unknown" or item["Name"] == "Specials":
            if item["Name"] == "Specials":
                parent_id = item['ParentId']
                season_name = "Season 0"
                season_id = item['Id']
                if parent_id not in series_dict:
                    series_dict[parent_id] = {}
                series_dict[parent_id][season_name] = season_id
            continue
        elif item['Name'].startswith("Season") or item['Name'].startswith("Partie"):
            parent_id = item['ParentId']
            season_name = item['Name']
            season_id = item['Id']
            if parent_id not in series_dict:
                series_dict[parent_id] = {}
            series_dict[parent_id][season_name] = season_id
        else:
            series_id = item['Id']
            series_name = item.get('Name')
            original_title = item.get('OriginalTitle')
            if series_id not in series_dict:
                series_dict[series_id] = {"Name": series_name}
            else:
                series_dict[series_id]["Name"] = series_name

            if original_title:
                series_dict[series_id]["OriginalTitle"] = original_title

            if 'Year' in item:
                series_dict[series_id]["Year"] = item['Year']

    result = []

    for parent_id, seasons in series_dict.items():
        if "Specials" in seasons:
            special_info = {
                "Id": seasons["Specials"],
                "Name": "Specials",
                "ParentId": parent_id,
                "Type": "Season"
            }
            result.append(special_info)

    for series_id, details in series_dict.items():
        if "Name" in details:
            series_info = {
                "Id": series_id,
                "Name": details["Name"]
            }
            if "OriginalTitle" in details:
                series_info["OriginalTitle"] = details["OriginalTitle"]
            if "Year" in details:
                series_info["Year"] = details["Year"]
            seasons = {season_name: season_id for season_name, season_id in details.items() if
                       season_name != "Name" and season_name != "OriginalTitle" and season_name != "Year" and season_name != "Specials"}
            if seasons:
                series_info.update(seasons)
            result.append(series_info)

    result.sort(key=lambda x: x['Name'])

    for boxset in boxsets:
        boxset_info = {
            "Id": boxset['Id'],
            "Name": boxset['Name'].replace(" Filmreihe", "").replace(" Collection", ""),
            "Type": "BoxSet"
        }
        if "OriginalTitle" in boxset:
            boxset_info["OriginalTitle"] = boxset["OriginalTitle"]
        if "Year" in boxset:
            boxset_info["Year"] = boxset["Year"]
        result.append(boxset_info)

    return result

def save_if_different(output_filename, new_data):
    if os.path.exists(output_filename):
        try:
            with open(output_filename, 'r', encoding='utf-8') as file:
                old_data = json.load(file)
        except Exception as e:
            print(f"Error loading old JSON file: {e}")
            old_data = None

        if old_data == new_data:
            print("No changes detected, not saving the file.")
            return
        else:
            print("Changes detected, saving the new file.")

            if os.path.exists('./missing_folders.txt'):
                os.remove('./missing_folders.txt')

            clean_json_names(output_filename)
            assign_images_and_update_jellyfin(output_filename, jellyfin_url, api_key)

            if missing_folders:

                if os.path.exists('./missing_folders.txt'):
                    os.remove('./missing_folders.txt')

                with open("./missing_folders.txt", 'a', encoding='utf-8') as f:
                    for missing in missing_folders:
                        f.write(missing + "\n")
    else:
        print("No old file found, saving the new file.")

    try:
        with open(output_filename, 'w', encoding='utf-8') as outfile:
            json.dump(new_data, outfile, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving JSON file: {e}")
