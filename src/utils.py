# src/utils.py
import os
from datetime import datetime


def log(message: str, success: bool = True, details: str = None):
    """
    Log a message to the processing.log file.

    Args:
    message (str): The main message to log.
    success (bool): Whether the operation was successful. Defaults to True.
    details (str): Additional details to log. Defaults to None.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "ERROR"
    log_message = f"[{timestamp}] {status}: {message}"

    if details:
        log_message += f" -> {details}"

    log_message += "\n"

    with open('processing.log', 'a', encoding='utf-8') as f:
        f.write(log_message)

    # Also print to console for immediate feedback
    print(log_message.strip())


def ensure_dir(directory: str):
    """
    Ensure that a directory exists, creating it if necessary.

    Args:
    directory (str): The path to the directory to ensure exists.
    """
    if not os.path.exists(directory):
        os.makedirs(directory)
        log(f"Created directory: {directory}")


def get_content_type(file_path: str) -> str:
    """
    Determine the Content-Type based on the file extension.

    Args:
    file_path (str): The path to the file.

    Returns:
    str: The content type of the file.

    Raises:
    ValueError: If the file format is unsupported.
    """
    lower_path = file_path.lower()
    if lower_path.endswith('.png'):
        return 'image/png'
    elif lower_path.endswith(('.jpg', '.jpeg')):
        return 'image/jpeg'
    elif lower_path.endswith('.webp'):
        return 'image/webp'
    else:
        raise ValueError(f"Unsupported file format for {file_path}")
