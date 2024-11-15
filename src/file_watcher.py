import logging
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import platform

logger = logging.getLogger(__name__)


class CoverChangeHandler(FileSystemEventHandler):
    def __init__(self, cover_dir: Path):
        self.cover_dir = cover_dir
        self.changes_detected = False
        self._last_event_time = 0
        self._event_cooldown = 1  # 1 second cooldown between events

    def on_created(self, event):
        if self._should_process_event():
            path = Path(event.src_path)
            if path.is_relative_to(self.cover_dir):
                logger.info(f"New file/directory detected: {event.src_path}")
                self.changes_detected = True

    def on_modified(self, event):
        if not event.is_directory and self._should_process_event():
            path = Path(event.src_path)
            if path.is_relative_to(self.cover_dir):
                logger.info(f"File modified: {event.src_path}")
                self.changes_detected = True

    def on_moved(self, event):
        if self._should_process_event():
            dest_path = Path(event.dest_path)
            if dest_path.is_relative_to(self.cover_dir):
                logger.info(f"File/directory moved/renamed: {event.dest_path}")
                self.changes_detected = True

    def on_deleted(self, event):
        if self._should_process_event():
            path = Path(event.src_path)
            if path.is_relative_to(self.cover_dir):
                logger.info(f"File/directory deleted: {event.src_path}")
                self.changes_detected = True

    def _should_process_event(self) -> bool:
        """
        Implements cooldown logic to prevent multiple rapid-fire events
        """
        current_time = time.time()
        if current_time - self._last_event_time >= self._event_cooldown:
            self._last_event_time = current_time
            return True
        return False

    def reset_changes(self):
        self.changes_detected = False


class CoverMonitor:
    def __init__(self, cover_dir: Path):
        self.cover_dir = cover_dir
        self.event_handler = CoverChangeHandler(cover_dir)
        self.observer = Observer()

        # Nur auf Linux die inotify-Limits konfigurieren
        if platform.system() == 'Linux':
            self._configure_inotify_limits()

        self.observer.schedule(self.event_handler, str(cover_dir), recursive=True)

    def _configure_inotify_limits(self):
        """
        Configure higher inotify limits on Linux systems
        """
        try:
            import subprocess

            # Increase max_user_watches if needed
            subprocess.run(['sysctl', '-w', 'fs.inotify.max_user_watches=524288'],
                           check=True, capture_output=True)

            # Increase max_queued_events if needed
            subprocess.run(['sysctl', '-w', 'fs.inotify.max_queued_events=32768'],
                           check=True, capture_output=True)

            logger.info("Successfully configured inotify limits")
        except Exception as e:
            logger.warning(f"Failed to configure inotify limits: {e}")
            logger.warning("You might need to manually increase fs.inotify.max_user_watches")

    def start(self):
        """Start monitoring the directory"""
        self.observer.start()
        logger.info(f"Started monitoring COVER_DIR and subdirectories: {self.cover_dir}")

    def stop(self):
        """Stop monitoring the directory"""
        try:
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped file monitoring")
        except Exception as e:
            logger.error(f"Error stopping file monitor: {e}")

    def has_changes(self) -> bool:
        """Check if any changes were detected"""
        return self.event_handler.changes_detected

    def reset_changes(self):
        """Reset the change detection flag"""
        self.event_handler.reset_changes()