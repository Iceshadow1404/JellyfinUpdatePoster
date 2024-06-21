import json
import requests
import re

output_filename = 'sorted_series.json'


def start_get_and_save_series_and_movie(api_key, jellyfin_url):
    media_list = get_and_save_series_and_movies(api_key, jellyfin_url)
    if media_list:
        sort_series_and_movies('raw.json', output_filename)
    else:
        print("Failed to retrieve series and movies data.")


def get_and_save_series_and_movies(api_key, jellyfin_url):
    headers = {
        'X-Emby-Token': api_key
    }
    url = f'{jellyfin_url}/Items'
    params = {
        'Recursive': 'true',
        'IncludeItemTypes': 'Series,Season,Movie',  # Include Series, Seasons, and Movies
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

    # Create a list to store media information
    media_list = []
    for item in items:
        media_info = {
            'Id': item['Id'],
            'Name': item.get('Name'),  # Use 'Name' as default
            'ParentId': item.get('ParentId'),
            'Type': item['Type'],  # Add 'Type' to distinguish between Series, Season, and Movie
            'Year': item.get('ProductionYear', 'Unknown')  # Default to 'Unknown' if ProductionYear is not present
        }
        # Include OriginalTitle if available
        if 'OriginalTitle' in item:
            media_info['OriginalTitle'] = item['OriginalTitle']

        # Check and clean the Name field
        media_info['Name'] = clean_movie_name(media_info['Name'])

        media_list.append(media_info)

    # Save media information to a JSON file
    with open('raw.json', 'w', encoding='utf-8') as f:
        json.dump(media_list, f, ensure_ascii=False, indent=4)
    return media_list

def clean_movie_name(name):
    pattern = r' \(\d{4}\)$'
    return re.sub(pattern, '', name)


def sort_series_and_movies(input_filename, output_filename):
    try:
        with open(input_filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return

    series_dict = {}
    specials_dict = {}  # Dictionary to hold specials separately

    for item in data:
        if item['Name'] == "Season Unknown" or item["Name"] == "Specials":
            if item["Name"] == "Specials":
                # Handle Specials as Season 0
                parent_id = item['ParentId']
                season_name = "Season 0"
                season_id = item['Id']
                if parent_id not in series_dict:
                    series_dict[parent_id] = {}
                series_dict[parent_id][season_name] = season_id
            continue  # Skip "Season Unknown" entries
        elif item['Name'].startswith("Season") or item['Name'].startswith("Partie"):
            parent_id = item['ParentId']
            season_name = item['Name']
            season_id = item['Id']
            if parent_id not in series_dict:
                series_dict[parent_id] = {}
            series_dict[parent_id][season_name] = season_id
        else:
            series_id = item['Id']
            series_name = item.get('Name')  # Use 'Name' as default
            original_title = item.get('OriginalTitle')  # Get OriginalTitle if available
            if series_id not in series_dict:
                series_dict[series_id] = {"Name": series_name}
            else:
                series_dict[series_id]["Name"] = series_name

            if original_title:
                series_dict[series_id]["OriginalTitle"] = original_title

            if 'Year' in item:
                series_dict[series_id]["Year"] = item['Year']

    result = []

    # Add Specials (Season 0) to result
    for parent_id, seasons in series_dict.items():
        if "Specials" in seasons:
            special_info = {
                "Id": seasons["Specials"],
                "Name": "Specials",
                "ParentId": parent_id,
                "Type": "Season",
                "Year": 2022  # Adjust year as needed
            }
            result.append(special_info)

    # Add other seasons and series to result
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

    try:
        with open(output_filename, 'w', encoding='utf-8') as outfile:
            json.dump(result, outfile, indent=4)
    except Exception as e:
        print(f"Error saving JSON file: {e}")

