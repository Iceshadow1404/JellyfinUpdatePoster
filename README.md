# Jellyfin Cover Manager

This Python-based application is designed to automate the management and organization of media cover art, posters, and fanart for your Jellyfin libraries. It helps maintain a clean and consistent media artwork structure by processing, organizing, and managing cover images for movies, TV shows, and collections.

## Features

-  ZIP file support for batch processing (ThePosterDB, MediUX)
-  Management of unmatched content and automatic reprocessing
-  Blacklist system for problematic entries or libraries
-  Multi-language title support (TMDb API)
-  Movie, TV show, season, episode, and backdrop image management
-  Content change detection for Jellyfin libraries
-  Tracks missing and unused folders
-  Webhook support to trigger manual poster updates
-  Mediux set downloader

## Prerequisites

- Python 3.12+ (if running locally)
- Docker and Docker Compose (if running containerized)
- Jellyfin server
- [TMDb API key](https://developer.themoviedb.org/docs/getting-started)

## Installation

### Docker Installation (Recommended)

1. Create a `docker-compose.yml`:
```yaml
services:
  jellyfinupdateposter:
    image: iceshadow/jellyfinupdateposter:latest
    environment:
      - JELLYFIN_URL=http://jellyfin:8096
      - JELLYFIN_API_KEY=your-jellyfin-api-key
      - TMDB_API_KEY=your-tmdb-api-key
      - INCLUDE_EPISODES=false
      - TZ=Europe/Berlin
      - enable_webhook=false
    volumes:
      - ./your-local-path:/mount
    ports:
      - 8080:8080
    restart: unless-stopped
    command: "--force"
```

### Local Installation

1. Clone the repository:
```bash
git clone https://github.com/Iceshadow1404/JellyfinUpdatePoster
cd JellyfinUpdatePoster
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

### Using Environment Variables

Create a `.env` file in the root directory:
```bash
JELLYFIN_URL=http://your-jellyfin-server:8096
JELLYFIN_API_KEY=your-jellyfin-api-key
TMDB_API_KEY=your-tmdb-api-key
INCLUDE_EPISODES=false
enable_webhook=false
```

Required configuration variables:
- `JELLYFIN_URL`: The URL of your Jellyfin server
- `JELLYFIN_API_KEY`: Your Jellyfin API key
- `TMDB_API_KEY`: Your TMDb API key (required for multi-language support)
- `INCLUDE_EPISODES`: Whether to include episode images (true/false)

## Directory Structure

The application creates and manages the following directory structure:

```
├── RawCover/            # Drop your cover images here
├── Cover/               # Processed cover images
│   ├── Poster/          # Movie and TV show posters
│   ├── Collections/     # Collection artwork
│   └── No-Match/        # Unmatched artwork
├── Consumed/            # Processed source files
├── Replaced/            # Archived replaced artwork
```

## File Naming Conventions

The application supports various file naming patterns:

- Movie posters: `MovieName (Year).ext`
- TV Show posters: `ShowName (Year).ext`
- TV Show episodes: `ShowName/S01E02.ext`
- Season posters: `ShowName/Season01.ext`
- Collection posters: `CollectionName.ext`
- Backdrop images: `backdrop.ext`

## Usage

### Using Docker (Recommended)

Start the container:
```bash
docker compose up
```

Drop your image or .zip files into the `RawCover` folder.

### Running Locally

Run the main script:
```bash
python main.py
```

For a force update:
```bash
python main.py --force
```
Drop your image or .zip files into the `RawCover` folder.


## Features in Detail

### Multi-Language Support
- Fetches titles from TMDb in multiple languages (English, German, and alternative titles)
- Handles both original titles and localized versions

### Content Change Detection
- Monitors Jellyfin library for new or modified content
- Automatically triggers updates when changes are detected

### Image Management
- Supports multiple image types (Movie, TV show, season, episode, and backdrop)
- Tracks missing and unused folders
 
## Webhook Integration
- When enabled, sends POST requests to http://your_ip:8080/trigger to manually trigger cover processing. 
- Check status via GET request to /status.

## Mediux Downloader
- Simply paste a Mediux set link into the mediux.txt file

## Contact

- Feel free to message me on discord `Iceshadow_` if you have any questions or need help

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
