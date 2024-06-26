import os
import re
import shutil
from pathlib import Path
import zipfile
from PIL import Image

# Paths definition
raw_cover_dir = './RawCover'
cover_dir = './Cover'
movies_dir = os.path.join(cover_dir, 'Poster')
shows_dir = os.path.join(cover_dir, 'Poster')
collections_dir = os.path.join(cover_dir, 'Collections')
consumed_dir = './Consumed'
replaced_dir = './Replaced'

# Function to organize covers from a directory
def organize_covers():
    files_to_process = [item for item in os.listdir(raw_cover_dir) if os.path.isfile(os.path.join(raw_cover_dir, item))]

    if not files_to_process:
        log("No Files to process", success=False)

    for file_name in files_to_process:
        file_path = os.path.join(raw_cover_dir, file_name)

        try:
            if file_name.endswith('.zip'):
                process_zip_file(file_path)
            elif file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                process_image_file(file_path)

            shutil.move(file_path, os.path.join(consumed_dir, file_name))
            log(f"Processed: {file_name} -> Consumed/{file_name}")

        except Exception as e:
            log(f"Error processing {file_name}: {e}", success=False)


def process_zip_file(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            extracted_files = [file_info.filename for file_info in zip_ref.infolist()]
            is_series = any(re.match(r'.*Season (\d+)', filename) or "Specials" in filename for filename in extracted_files)
            has_collection = any("Collection" in filename or "Collections" in filename for filename in extracted_files)

            for filename in extracted_files:
                file_info = zip_ref.getinfo(filename)
                file_ext = Path(filename).suffix.lower()

                # Check if the file is an image file (PNG, JPG, JPEG, WebP)
                if file_ext in ('.png', '.jpg', '.jpeg', '.webp'):
                    # Determine target filename
                    if is_series:
                        series_match = re.match(r'(.+?) \((\d{4})\)', filename)
                        if series_match:
                            series_name, series_year = series_match.groups()
                            series_dir = os.path.join(shows_dir, f"{series_name} ({series_year})")
                            Path(series_dir).mkdir(parents=True, exist_ok=True)

                            season_match = re.match(r'.*Season (\d+)', filename)
                            if season_match:
                                season_number = int(season_match.group(1))
                                target_filename = f'Season{season_number:02}.jpg'
                            elif "Specials" in filename:
                                target_filename = f'Season00.jpg'
                            else:
                                target_filename = 'poster.jpg'

                            target_path = os.path.join(series_dir, target_filename)

                            if os.path.exists(target_path):
                                # Move existing file to ./Replaced
                                replaced_subdir = os.path.join(replaced_dir, f"{series_name} ({series_year})")
                                if not os.path.exists(replaced_subdir):
                                    os.makedirs(replaced_subdir)
                                # Generate a unique filename for the replaced file
                                replaced_filename = generate_unique_filename(replaced_subdir, target_filename)
                                shutil.move(target_path, os.path.join(replaced_subdir, replaced_filename))
                                log(f"Moved existing file: {target_path} -> {replaced_subdir}/{replaced_filename}")

                            with zip_ref.open(filename) as source, open(target_path, 'wb') as target:
                                shutil.copyfileobj(source, target)
                                log(f"Processed: {filename} -> {series_dir}/{target_filename}", details=f"{series_dir}/{target_filename}")

                    else:
                        movie_match = re.match(r'(.+?) \((\d{4})\)', filename)
                        if movie_match:
                            movie_name, movie_year = movie_match.groups()
                            movie_dir = os.path.join(movies_dir, f"{movie_name} ({movie_year})")
                            Path(movie_dir).mkdir(parents=True, exist_ok=True)

                            # Check if it's the main poster
                            if "Season" not in filename and "Specials" not in filename:
                                target_filename = 'poster.jpg'
                            else:
                                target_filename = os.path.splitext(filename)[0] + '.jpg'

                            target_path = os.path.join(movie_dir, target_filename)

                            if os.path.exists(target_path):
                                # Move existing file to ./Replaced
                                replaced_subdir = os.path.join(replaced_dir, f"{movie_name} ({movie_year})")
                                if not os.path.exists(replaced_subdir):
                                    os.makedirs(replaced_subdir)
                                # Generate a unique filename for the replaced file
                                replaced_filename = generate_unique_filename(replaced_subdir, target_filename)
                                shutil.move(target_path, os.path.join(replaced_subdir, replaced_filename))
                                log(f"Moved existing file: {target_path} -> {replaced_subdir}/{replaced_filename}")

                            with zip_ref.open(filename) as source, open(target_path, 'wb') as target:
                                shutil.copyfileobj(source, target)
                                log(f"Processed: {filename} -> {movie_dir}/{target_filename}", details=f"{movie_dir}/{target_filename}")

                else:
                    log(f"Ignored file: {filename} (not a supported image format)", success=False)

                if has_collection:
                    for filename in extracted_files:
                        if "Collection" in filename or "Collections" in filename:
                            collection_match = re.match(r'(.+?) Collection', filename)
                            if collection_match:
                                collection_name = collection_match.group(1)
                                collection_dir = os.path.join(collections_dir, collection_name)
                                Path(collection_dir).mkdir(parents=True, exist_ok=True)
                                target_filename = 'poster.jpg'
                                target_path = os.path.join(collection_dir, target_filename)

                                if os.path.exists(target_path):
                                    # Move existing file to ./Replaced
                                    replaced_subdir = os.path.join(replaced_dir, collection_name)
                                    if not os.path.exists(replaced_subdir):
                                        os.makedirs(replaced_subdir)
                                    # Generate a unique filename for the replaced file
                                    replaced_filename = generate_unique_filename(replaced_subdir, target_filename)
                                    shutil.move(target_path, os.path.join(replaced_subdir, replaced_filename))
                                    log(f"Moved existing file: {target_path} -> {replaced_subdir}/{replaced_filename}")

                                with zip_ref.open(filename) as source, open(target_path, 'wb') as target:
                                    shutil.copyfileobj(source, target)
                                    log(f"Processed: {filename} -> {collection_dir}/{target_filename}",
                                        details=f"{collection_dir}/{target_filename}")

    except zipfile.BadZipFile:
        log(f"Error: {zip_path} is not a valid zip file.", success=False)
    except Exception as e:
        log(f"Error processing {zip_path}: {e}", success=False)


def process_image_file(image_path):
    try:
        with Image.open(image_path) as img:
            img_basename = os.path.basename(image_path)
            movie_name, movie_year = extract_movie_info(img_basename)
            movie_dir = os.path.join(movies_dir, f"{movie_name} ({movie_year})")
            Path(movie_dir).mkdir(parents=True, exist_ok=True)
            target_filename = 'poster' + os.path.splitext(img_basename)[1].lower()
            target_path = os.path.join(movie_dir, target_filename)

            # Check if target file already exists
            if os.path.exists(target_path):
                # Move existing file to ./Replaced
                replaced_subdir = os.path.join(replaced_dir, f"{movie_name} ({movie_year})")
                if not os.path.exists(replaced_subdir):
                    os.makedirs(replaced_subdir)
                # Generate a unique filename for the replaced file
                replaced_filename = generate_unique_filename(replaced_subdir, target_filename)
                shutil.move(target_path, os.path.join(replaced_subdir, replaced_filename))
                log(f"Moved existing file: {target_path} -> {replaced_subdir}/{replaced_filename}")

            # Now copy the new file to the target directory
            shutil.copyfile(image_path, target_path)

            # Convert to JPG if it's not already in JPG format
            if not target_filename.endswith('.jpg'):
                converted_path = convert_to_jpg(target_path)
                if converted_path:
                    target_path = converted_path
                    target_filename = os.path.basename(converted_path)

            log(f"Processed: {img_basename} -> {movie_dir}/{target_filename}", details=f"{movie_dir}/{target_filename}")

    except Exception as e:
        log(f"Error processing image file {image_path}: {e}", success=False)

def generate_unique_filename(directory, filename):
    # Generate a unique filename by appending a number
    base_name, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(directory, new_filename)):
        new_filename = f"{base_name}_{counter}{ext}"
        counter += 1
    return new_filename



def extract_movie_info(filename):
    movie_match = re.match(r'(.+?) \((\d{4})\)', filename)
    if movie_match:
        movie_name, movie_year = movie_match.groups()
    else:
        movie_name = filename.split('(')[0].strip()
        movie_year = 'Unknown'
    return movie_name, movie_year


def convert_to_jpg(image_path):
    try:
        img = Image.open(image_path)

        if img.format != 'JPEG' and not image_path.lower().endswith('.jpeg'):
            jpg_path = os.path.splitext(image_path)[0] + '.jpg'
            img.convert('RGB').save(jpg_path, 'JPEG')  # Als JPEG speichern

            # Originaldatei entfernen
            os.remove(image_path)

            log(f"Converted {image_path} to JPG format and deleted original.")

            return jpg_path

        if img.format == 'JPEG' or image_path.lower().endswith('.jpeg'):
            jpg_path = os.path.splitext(image_path)[0] + '.jpg'
            img.convert('RGB').save(jpg_path, 'JPEG')  # Als JPEG speichern

            # Originaldatei entfernen
            os.remove(image_path)

            log(f"Converted {image_path} to JPG format and deleted original.")

    except Exception as e:
        log(f"Error converting {image_path} to JPG: {e}", success=False)

    return None


def log(message, success=True, details=None):
    with open('processing.log', 'a', encoding='utf-8') as f:
        if success:
            if details:
                f.write(f"SUCCESS: {message} -> {details}\n")
            else:
                f.write(f"SUCCESS: {message}\n")
        else:
            f.write(f"ERROR: {message}\n")