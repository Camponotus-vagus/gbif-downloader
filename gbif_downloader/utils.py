"""
Utility functions and logging configuration for GBIF Downloader.
"""

import logging
import sys
from datetime import datetime
from functools import wraps
from time import sleep
from typing import Callable, TypeVar

# Type variable for generic retry decorator
T = TypeVar("T")


def setup_logging(
    level: int = logging.INFO,
    log_file: str | None = None,
    verbose: bool = False,
) -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        level: Logging level (default: INFO)
        log_file: Optional file path to write logs
        verbose: If True, set level to DEBUG

    Returns:
        Configured logger instance
    """
    if verbose:
        level = logging.DEBUG

    # Create logger
    logger = logging.getLogger("gbif_downloader")
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler with color support
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Format: timestamp - level - message
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    """Get the application logger."""
    return logging.getLogger("gbif_downloader")


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """
    Decorator for retrying a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for each subsequent delay
        exceptions: Tuple of exception types to catch

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            logger = get_logger()
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(f"Failed after {max_retries + 1} attempts: {e}")
                        raise

                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    sleep(delay)
                    delay *= backoff_factor

            # This should never be reached, but just in case
            raise RuntimeError("Retry loop exited unexpectedly")

        return wrapper

    return decorator


def format_count(count: int) -> str:
    """
    Format a count with thousands separators.

    Args:
        count: The number to format

    Returns:
        Formatted string (e.g., "1,234,567")
    """
    return f"{count:,}"


def validate_year(year: int, field_name: str = "year") -> int:
    """
    Validate a year value.

    Args:
        year: Year to validate
        field_name: Name of the field for error messages

    Returns:
        The validated year

    Raises:
        ValueError: If year is invalid
    """
    current_year = datetime.now().year

    if not isinstance(year, int):
        raise ValueError(f"{field_name} must be an integer, got {type(year).__name__}")

    if year < 1700:
        raise ValueError(f"{field_name} must be >= 1700, got {year}")

    if year > current_year + 1:
        raise ValueError(
            f"{field_name} cannot be in the future (max: {current_year}), got {year}"
        )

    return year


def validate_positive_int(value: int, field_name: str, allow_zero: bool = False) -> int:
    """
    Validate that a value is a positive integer.

    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        allow_zero: If True, allow zero as a valid value

    Returns:
        The validated value

    Raises:
        ValueError: If value is invalid
    """
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer, got {type(value).__name__}")

    min_val = 0 if allow_zero else 1
    if value < min_val:
        raise ValueError(f"{field_name} must be >= {min_val}, got {value}")

    return value


def clean_string_list(items: str | list[str] | None) -> list[str]:
    """
    Clean and normalize a list of strings.

    Handles:
    - None -> empty list
    - Comma-separated string -> list
    - List with empty strings -> filtered list

    Args:
        items: Input string or list

    Returns:
        Clean list of non-empty strings
    """
    if items is None:
        return []

    if isinstance(items, str):
        items = items.split(",")

    return [item.strip().lower() for item in items if item and item.strip()]


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    Sanitize a string for use as a filename.

    Args:
        name: Input string
        max_length: Maximum allowed length

    Returns:
        Safe filename string
    """
    # Replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        name = name.replace(char, "_")

    # Remove leading/trailing whitespace and dots
    name = name.strip().strip(".")

    # Truncate if too long
    if len(name) > max_length:
        name = name[:max_length]

    return name or "unnamed"


def estimate_download_time(record_count: int, records_per_second: float = 100) -> str:
    """
    Estimate download time for a given number of records.

    Args:
        record_count: Number of records to download
        records_per_second: Estimated processing speed

    Returns:
        Human-readable time estimate
    """
    seconds = record_count / records_per_second

    if seconds < 60:
        return f"~{int(seconds)} seconds"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"~{int(minutes)} minutes"
    else:
        hours = seconds / 3600
        return f"~{hours:.1f} hours"


class ProgressTracker:
    """
    Track progress of a long-running operation.

    Attributes:
        total: Total number of items
        current: Current item number
        start_time: When tracking started
    """

    def __init__(self, total: int = 0):
        """
        Initialize progress tracker.

        Args:
            total: Total number of items (can be updated later)
        """
        self.total = total
        self.current = 0
        self.start_time = datetime.now()
        self._callbacks: list[Callable[[int, int], None]] = []

    def update(self, current: int | None = None, increment: int = 1) -> None:
        """
        Update progress.

        Args:
            current: Set current value directly (optional)
            increment: Amount to increment by (used if current is None)
        """
        if current is not None:
            self.current = current
        else:
            self.current += increment

        # Notify callbacks
        for callback in self._callbacks:
            callback(self.current, self.total)

    def set_total(self, total: int) -> None:
        """Update the total count."""
        self.total = total

    def add_callback(self, callback: Callable[[int, int], None]) -> None:
        """
        Add a progress callback function.

        Args:
            callback: Function that takes (current, total) arguments
        """
        self._callbacks.append(callback)

    @property
    def percentage(self) -> float:
        """Get progress as a percentage (0-100)."""
        if self.total == 0:
            return 0.0
        return min(100.0, (self.current / self.total) * 100)

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def eta_seconds(self) -> float | None:
        """
        Estimate remaining time in seconds.

        Returns:
            Estimated seconds remaining, or None if not calculable
        """
        if self.current == 0 or self.total == 0:
            return None

        elapsed = self.elapsed_seconds
        rate = self.current / elapsed
        remaining = self.total - self.current

        return remaining / rate if rate > 0 else None

    def format_status(self) -> str:
        """Get a formatted status string."""
        pct = self.percentage
        eta = self.eta_seconds

        status = f"{self.current:,}/{self.total:,} ({pct:.1f}%)"

        if eta is not None:
            if eta < 60:
                status += f" - ETA: {int(eta)}s"
            elif eta < 3600:
                status += f" - ETA: {int(eta / 60)}m"
            else:
                status += f" - ETA: {eta / 3600:.1f}h"

        return status
