import os
import re
import shutil
from pathlib import Path
import zipfile
from PIL import Image  # Pillow library for image file handling

# Paths definition
raw_cover_dir = './RawCover'
cover_dir = './Cover'
movies_dir = os.path.join(cover_dir, './Poster')
shows_dir = os.path.join(cover_dir, './Poster')
collections_dir = os.path.join(cover_dir, 'Collections')
consumed_dir = './Consumed'

# Function to organize covers from a directory
def organize_covers():
    # Ensure target directories exist
    for dir_path in [movies_dir, shows_dir, collections_dir, consumed_dir, raw_cover_dir]:
        if not os.path.exists(dir_path):
            #os.makedirs(dir_path)
            print("First Startup")


    # List of files to process (both zip and individual image files)
    files_to_process = [item for item in os.listdir(raw_cover_dir) if os.path.isfile(os.path.join(raw_cover_dir, item))]

    for file_name in files_to_process:
        file_path = os.path.join(raw_cover_dir, file_name)

        if file_name.endswith('.zip'):
            process_zip_file(file_path)
        elif file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            process_image_file(file_path)

        # Move processed file to /Consumed directory
        shutil.move(file_path, os.path.join(consumed_dir, file_name))

def process_zip_file(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            extracted_files = [file_info.filename for file_info in zip_ref.infolist()]

            # Check if it's a series (at least one season file in ZIP)
            is_series = any(re.match(r'.*Season (\d+)', filename) or "Specials" in filename for filename in extracted_files)

            # Check if there's a collection
            has_collection = any("Collection" in filename or "Collections" in filename for filename in extracted_files)

            for filename in extracted_files:
                file_info = zip_ref.getinfo(filename)
                file_ext = Path(filename).suffix

                if is_series:
                    # It's a series
                    series_match = re.match(r'(.+?) \((\d{4})\)', filename)
                    if series_match:
                        series_name, series_year = series_match.groups()
                        series_dir = os.path.join(shows_dir, f"{series_name} ({series_year})")
                        Path(series_dir).mkdir(parents=True, exist_ok=True)

                        # Check if it's a season
                        season_match = re.match(r'.*Season (\d+)', filename)
                        if season_match:
                            season_number = int(season_match.group(1))
                            target_filename = f'Season{season_number:02}{file_ext}'
                        elif "Specials" in filename:
                            target_filename = f'Season00{file_ext}'
                        else:
                            target_filename = f'poster{file_ext}'

                        target_path = os.path.join(series_dir, target_filename)

                        # Extract and copy file
                        with zip_ref.open(filename) as source, open(target_path, 'wb') as target:
                            shutil.copyfileobj(source, target)

                else:
                    # It's a movie
                    movie_match = re.match(r'(.+?) \((\d{4})\)', filename)
                    if movie_match:
                        movie_name, movie_year = movie_match.groups()
                        movie_dir = os.path.join(movies_dir, f"{movie_name} ({movie_year})")
                        Path(movie_dir).mkdir(parents=True, exist_ok=True)
                        target_filename = f'poster{file_ext}'
                        target_path = os.path.join(movie_dir, target_filename)

                        # Extract and copy file
                        with zip_ref.open(filename) as source, open(target_path, 'wb') as target:
                            shutil.copyfileobj(source, target)

            # Process collections after movies are processed
            if has_collection:
                for filename in extracted_files:
                    if "Collection" in filename or "Collections" in filename:
                        collection_match = re.match(r'(.+?) Collection', filename)
                        if collection_match:
                            collection_name = collection_match.group(1)
                            collection_dir = os.path.join(collections_dir, collection_name)
                            Path(collection_dir).mkdir(parents=True, exist_ok=True)
                            target_filename = 'poster.png'
                            target_path = os.path.join(collection_dir, target_filename)

                            with zip_ref.open(filename) as source, open(target_path, 'wb') as target:
                                shutil.copyfileobj(source, target)

    except zipfile.BadZipFile:
        print(f"Error: {zip_path} is not a valid zip file.")
    except Exception as e:
        print(f"Error processing {zip_path}: {e}")

def process_image_file(image_path):
    try:
        # Open image file using Pillow
        with Image.open(image_path) as img:
            img_basename = os.path.basename(image_path)
            movie_name, movie_year = extract_movie_info(img_basename)

            # Create movie directory
            movie_dir = os.path.join(movies_dir, f"{movie_name} ({movie_year})")
            Path(movie_dir).mkdir(parents=True, exist_ok=True)

            # Ensure the image is saved as "poster"
            target_filename = 'poster' + os.path.splitext(img_basename)[1]
            target_path = os.path.join(movie_dir, target_filename)

            # Copy image file to movie directory
            shutil.copyfile(image_path, target_path)

    except Exception as e:
        print(f"Error processing image file {image_path}: {e}")

def extract_movie_info(filename):
    # Extract movie name and year from filename
    movie_match = re.match(r'(.+?) \((\d{4})\)', filename)
    if movie_match:
        movie_name, movie_year = movie_match.groups()
    else:
        # If no year found, assume it's part of the movie name
        movie_name = filename.split('(')[0].strip()
        movie_year = 'Unknown'
    return movie_name, movie_year

if __name__ == "__main__":
    organize_covers()

    # Print the directories created
    print("Created directories:")

    # Movies subdirectories
    print(f"- {movies_dir}")
    movie_subdirs = os.listdir(movies_dir)
    for subdir in movie_subdirs:
        print(f"  - {os.path.join(movies_dir, subdir)}")

    # Shows subdirectories
    print(f"- {shows_dir}")
    show_subdirs = os.listdir(shows_dir)
    for subdir in show_subdirs:
        print(f"  - {os.path.join(shows_dir, subdir)}")

    # Collections subdirectories
    print(f"- {collections_dir}")
    collection_subdirs = os.listdir(collections_dir)
    for subdir in collection_subdirs:
        print(f"  - {os.path.join(collections_dir, subdir)}")