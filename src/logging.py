import logging

# ANSI escape sequences for colors
class ColoredFormatter(logging.Formatter):
    # Define colors
    COLOR_CODES = {
        logging.INFO: "\033[92m",  # Green
        logging.WARNING: "\033[93m",  # Yellow
        logging.ERROR: "\033[91m",  # Red
        'RESET': "\033[0m"  # Reset to default
    }

    def format(self, record):
        # Set the color based on the log level
        color = self.COLOR_CODES.get(record.levelno, self.COLOR_CODES['RESET'])
        reset = self.COLOR_CODES['RESET']

        # Format the original log message
        message = super().format(record)

        # Return the colored log message
        return f"{color}{message}{reset}"


def setup_logging():
    # Create a custom formatter
    formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

    # Set up the handler with the formatter
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Configure logging with the custom handler
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler]
    )

if __name__ == "__main__":
    setup_logging()
