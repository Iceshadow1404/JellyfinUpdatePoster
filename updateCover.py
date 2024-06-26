import os
import json
import requests
from base64 import b64encode

with open("config.json", 'r') as file:
    data = json.load(file)

jellyfin_url = data["jellyfin_url"]
api_key = data["api_key"]

# Define paths and directories
cover_dir = './Cover'
poster_dir = os.path.join(cover_dir, 'Poster')
collections_dir = os.path.join(cover_dir, 'Collections')

missing_folders = []

def clean_json_names(json_filename):
    json_path = os.path.join(os.getcwd(), json_filename)

    # Ensure the JSON file exists
    if not os.path.exists(json_path):
        print(f"The JSON file {json_filename} could not be found.")
        (print("Don't panic if this is your first time using this script; just wait 60 seconds for new instructions"))
        return

    # Load JSON data
    with open(json_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    # Clean names in the JSON data
    for series in json_data:
        if 'Name' in series:
            series['Name'] = series['Name'].replace(':', '').replace('&', '').replace("'", '').replace("!", '')
        if 'OriginalTitle' in series:
            series['OriginalTitle'] = series['OriginalTitle'].replace(':', '').replace('&', '').replace("'", '').replace("!", '')


    # Save cleaned data back to the JSON file
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=4)


def assign_images_and_update_jellyfin(json_filename, jellyfin_url, api_key):
    global missing_folders  # Ensure we are using the global missing_folders variable

    json_path = os.path.join(json_filename)

    # Ensure the JSON file exists
    if not os.path.exists(json_path):
        print(f"The JSON file {json_filename} could not be found.")
        return

    # Load JSON data
    with open(json_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    # Process each series or movie in the JSON file
    for item in json_data:
        item_name = item.get('Name').strip()
        item_original_title = item.get('OriginalTitle',
                                       item_name).strip()  # Use strip() to remove leading/trailing spaces
        item_year = item.get('Year')
        item_id = item.get('Id')
        item_type = item.get('Type')

        if not item_original_title or not item_year or not item_id:
            print(f"Invalid data found for item: {item}. Skipping.")
            continue

        # Check if the item is a show, movie, or boxset based on the directory existence
        item_dir = None
        if item_type == "BoxSet":
            if os.path.exists(os.path.join(collections_dir, item_name)):
                item_dir = os.path.join(collections_dir, item_name)

            else:
                print(f"Collection not found for item: {item_name}. Skipping.")
                missing_folder = f"Collection Folder: {item_name}"
                missing_folders.append(missing_folder)
                continue

        elif os.path.exists(os.path.join(poster_dir, f"{item_original_title} ({item_year})")):
            item_dir = os.path.join(poster_dir, f"{item_original_title} ({item_year})")
        elif os.path.exists(os.path.join(poster_dir, f"{item_name} ({item_year})")):
            item_dir = os.path.join(poster_dir, f"{item_name} ({item_year})")

        else:
            missing_folder = f"Poster Folder: {item_original_title} ({item_year}) / {item_name} ({item_year})"
            print(f"Folder not found for item: {missing_folder}. Skipping.")
            missing_folders.append(missing_folder)
            continue

        # Find main poster for the item
        main_poster_path = None
        for poster_filename in ['poster.png', 'poster.jpeg', 'poster.jpg', 'poster.webp']:
            if item_dir is not None and poster_filename is not None:
                poster_path = os.path.join(item_dir, poster_filename)
                if os.path.exists(poster_path):
                    main_poster_path = poster_path
                    break


        if main_poster_path:
            # Update Jellyfin with main poster
            update_jellyfin(item_id, main_poster_path, item_original_title, api_key, jellyfin_url)
        else:
            print(f"Main poster not found for item: {item_original_title} ({item_year})")

        # Process each season/image for the item
        for key, image_id in item.items():
            if key.startswith("Season") and image_id:  # Process seasons for shows
                season_number = key.split(" ")[-1]
                season_image_filename = f'Season{season_number.zfill(2)}'
                season_image_path = None

                for ext in ['png', 'jpg', 'jpeg', 'webp']:
                    season_image_path = os.path.join(item_dir, f"{season_image_filename}.{ext}")
                    if os.path.exists(season_image_path):
                        break

                if not os.path.exists(season_image_path):
                    print(f"Season image not found for item - {item_original_title} ({item_year}) - {key}")
                    continue

                # Update Jellyfin with season image
                update_jellyfin(image_id, season_image_path, f"{item_original_title} ({item_year}) - {key}", api_key, jellyfin_url)

            elif key == 'Images' and isinstance(image_id, list):  # Process images for movies
                for image_info in image_id:
                    if 'Type' in image_info and 'Id' in image_info and 'Path' in image_info:
                        image_type = image_info['Type']
                        image_id = image_info['Id']
                        image_path = os.path.join(item_dir, image_info['Path'])

                        if not os.path.exists(image_path):
                            print(f"Image not found for item - {item_original_title} ({item_year}): {image_path}")
                            continue

                        # Update Jellyfin with movie image
                        update_jellyfin(image_id, image_path, f"{item_original_title} ({item_year}) - {image_type}", api_key, jellyfin_url)
                    else:
                        print(f"Invalid image data found for item - {item_original_title} ({item_year})")

    print(f"Processing completed for {json_filename}")
    print("updated all posters")

def update_jellyfin(id, image_path, item_name, api_key, jellyfin_url):
    endpoint = f'/Items/{id}/Images/Primary/0'
    url = jellyfin_url + endpoint
    headers = {'X-Emby-Token': api_key}

    if not os.path.exists(image_path):
        print(f"Image file not found: {image_path}. Skipping.")
        return

    with open(image_path, 'rb') as file:
        image_data = file.read()

        # Determine content type based on file extension
        content_type = get_content_type(image_path)
        headers['Content-Type'] = content_type

        image_base64 = b64encode(image_data)

    response = requests.post(url, headers=headers, data=image_base64)
    if response.status_code == 204:
        print(f'Updated image for {item_name} successfully.')
        #log(f'Updated image for {item_name} successfully.')
    else:
        print(f'Error updating image for {item_name}. Status Code: {response.status_code}')
        print(f'Response: {response.text}')


def get_content_type(file_path):
    # Determine the Content-Type based on the file extension
    if file_path.lower().endswith('.png'):
        return 'image/png'
    elif file_path.lower().endswith(('.jpg', '.jpeg')):
        return 'image/jpeg'
    elif file_path.lower().endswith('.webp'):
        return 'image/webp'
    else:
        raise ValueError(f"Unsupported file format for {file_path}")