from typing import List, Optional
import datetime
import logging

from src.config import RAW_TIMES

logger = logging.getLogger(__name__)

def is_valid_time_format(time_str: str) -> bool:
    """Check if the time string matches the required format (HH:MM)"""
    try:
        hours, minutes = map(int, time_str.split(':'))
        return 0 <= hours < 24 and 0 <= minutes < 60
    except ValueError:
        return False


# Process scheduled times from environment
SCHEDULED_TIMES = []

for time_str in RAW_TIMES:
    if is_valid_time_format(time_str):
        SCHEDULED_TIMES.append(time_str)
    else:
        logger.error(f"Invalid time format in SCHEDULED_TIMES: '{time_str}'. Expected format: HH:MM (24-hour)")

# Sort times for consistent ordering
SCHEDULED_TIMES.sort()


def get_next_scheduled_time() -> Optional[datetime.datetime]:
    """Calculate the next scheduled execution time"""
    if not SCHEDULED_TIMES:
        return None

    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M")

    # Find the next scheduled time today
    for time_str in SCHEDULED_TIMES:
        hours, minutes = map(int, time_str.split(':'))
        next_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        if next_time > now:
            return next_time

    # If no times left today, get the first time tomorrow
    tomorrow = now + datetime.timedelta(days=1)
    hours, minutes = map(int, SCHEDULED_TIMES[0].split(':'))
    return tomorrow.replace(hour=hours, minute=minutes, second=0, microsecond=0)

def is_scheduled_time() -> bool:
    """Check if current time matches any of the scheduled execution times"""
    if not SCHEDULED_TIMES:
        return False

    current_time = datetime.datetime.now().strftime("%H:%M")
    return current_time in SCHEDULED_TIMES


def format_time_until_next(next_time: Optional[datetime.datetime]) -> str:
    """Format the time until next scheduled execution"""
    if not next_time:
        return "No scheduled executions"

    now = datetime.datetime.now()
    time_diff = next_time - now

    hours, remainder = divmod(time_diff.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if time_diff.days > 0:
        return f"Next scheduled execution in {time_diff.days}d {hours}h {minutes}m"
    else:
        return f"Next scheduled execution in {hours}h {minutes}m {seconds}s"

