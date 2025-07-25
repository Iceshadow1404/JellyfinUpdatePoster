# Jellyfin Update Poster

A Python application to automate the management of cover art, posters, and fanart for your Jellyfin libraries.

Primarily made for Posters from [ThePosterDB](https://theposterdb.com/) and [Mediux](https://mediux.pro/)

-----

## Features

  * **Comprehensive Image Management**: Handles posters, backdrops, and other art for movies, TV shows, seasons, and episodes.
  * **Batch Processing**: Supports `.zip` files from sources like ThePosterDB and MediUX for easy bulk imports.
  * **Automated Matching**: Automatically processes and matches artwork to the correct media items. Includes a system for managing unmatched content for later reprocessing.
  * **Multi-Language Support**: Utilizes the TMDb API to recognize titles in multiple languages.
  * **Content Change Detection**: Monitors your Jellyfin libraries for new or modified content and triggers updates automatically.
  * **Mediux Downloader**: Directly downloads Mediux sets by adding a link to `mediux.txt`.
  * **Webhook Triggers**: An optional webhook to manually trigger poster updates via a POST request.

-----

## Prerequisites

  * Python 3.12+ (for local installation)
  * Docker and Docker Compose (recommended)
  * A running Jellyfin server
  * A [TMDb API key](https://developer.themoviedb.org/docs/getting-started)

-----

## Installation and Configuration

The recommended method is to use Docker.

### Docker (Recommended)

1.  Create a `docker-compose.yml` and configure it with your environment variables.

    ```yaml
    services:
      jellyfinupdateposter:
        image: iceshadow/jellyfinupdateposter:latest
        container_name: jellyfinupdateposter
        restart: unless-stopped
        environment:
          - JELLYFIN_URL=http://jellyfin:8096
          - JELLYFIN_API_KEY=your-jellyfin-api-key
          - TMDB_API_KEY=your-tmdb-api-key
          - INCLUDE_EPISODES=false
          - TZ=Europe/Berlin
          - ENABLE_WEBHOOK=false
          - SCHEDULED_TIMES=06:00,12:00,18:00 # Optional
        volumes:
          - ./your-local-path:/mount
        ports:
          - "8080:8080" # Required only if ENABLE_WEBHOOK=true
    ```

2.  Start the container.

    ```bash
    docker compose up -d
    ```

### Local Installation

1.  Clone the repository and install dependencies.
    ```bash
    git clone https://github.com/Iceshadow1404/JellyfinUpdatePoster
    cd JellyfinUpdatePoster
    pip install -r requirements.txt
    ```
2.  Create a `.env` file in the root directory and add your configuration variables (see below).
3.  Run the script. To force an update, use the `--force` flag.
    ```bash
    python main.py
    ```

### Environment Variables

  * `JELLYFIN_URL`: **Required.** The URL of your Jellyfin server.
  * `JELLYFIN_API_KEY`: **Required.** Your Jellyfin API key.
  * `TMDB_API_KEY`: **Required.** Your TMDb API key.
  * `INCLUDE_EPISODES`: Set to `true` or `false` to manage episode images. Defaults to `false`.
  * `ENABLE_WEBHOOK`: Set to `true` to enable the webhook trigger. Defaults to `false`.
  * `SCHEDULED_TIMES`: Optional comma-separated list of `HH:MM` times to run scheduled updates.
  * `TZ`: Optional timezone for scheduling, e.g., `America/New_York`.

-----

## Usage

The primary workflow is to **place your image files or `.zip` archives into the `RawCover` directory**. The application processes them automatically based on the file naming conventions.

### File Naming Conventions

  * **Movie Poster**: `MovieName (Year)/poster.ext`
  * **TV Show Poster**: `ShowName (Year)/poster.ext`
  * **Season Poster**: `ShowName (Year)/Season01.ext`
  * **Episode Image**: `ShowName (Year)/S01E02.ext`
  * **Collection Poster**: `poster.ext`
  * **Backdrop**: `backdrop.ext` (placed in the same folder as a poster)

### Directory Structure

The application creates and uses the following directory structure inside your mounted volume (`/mount`):

```
.
├── RawCover/      # Drop new image files and ZIPs here
├── Cover/         # Processed and organized artwork
├── Consumed/      # Source files are moved here after processing
└── Replaced/      # Old artwork is archived here when updated
```

-----

## Contact

For questions or help, you can message `iceshadow_` on Discord or create an issue.

## License

This project is licensed under the MIT License.
