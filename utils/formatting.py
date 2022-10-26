import logging
import sys
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Generator, SupportsInt

from .enums import PrintColours
from .types import Post

class GClassLogging(logging.Formatter):
    """
    Custom colour formatter for GClass's logging setup
    """
    
    _ = "#" if sys.platform == "win32" else "-"
    FMT = f"%Y/%{_}m/%{_}d %{_}I:%M:%S %p"
    
    COLOURS = {
        logging.DEBUG: PrintColours.WHITE,
        logging.INFO: PrintColours.BLUE,
        logging.WARNING: PrintColours.YELLOW,
        logging.ERROR: PrintColours.RED,
        logging.CRITICAL: PrintColours.RED + PrintColours.BOLD
    }
    
    def __init__(self):
        super().__init__(
            "|{levelname:<8}|",
            style="{"
        )
    
    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.COLOURS[record.levelno]
        colour = PrintColours.WHITE if record.levelno < logging.ERROR else PrintColours.RED
        formatter = logging.Formatter(
            log_fmt + self._fmt + "{asctime}" + colour + "{message}" + PrintColours.WHITE,
            datefmt=f"{PrintColours.YELLOW} [{datetime.now().strftime(self.FMT)}] ",
            style="{"
        )
        
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f"{PrintColours.RED}{text}{PrintColours.WHITE}"
        
        ret = formatter.format(record)
        record.exc_text = None
        return ret


def format_google_time(post: Post) -> datetime:
    """
    Formats a time string returned from Google's APIs
    
    Arguments
    ---------
    post: `Post`
        The classroom post to format
    
    Returns
    -------
    format_google_time: `datetime`
        A timezone-aware datetime object in UTC
    """
    parse = partial(datetime.strptime, post["creationTime"])
    try:
        parsed = parse("%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        parsed = parse("%Y-%m-%dT%H:%M:%SZ")
    
    return parsed.replace(tzinfo=timezone.utc)


def all_casings(input_string: str) -> Generator[str, None, None]:
    """
    A generator that yields every combination of lowercase and uppercase in a given string

    Arguments
    ---------
    input_string: `str`
        The string to iterate through

    Returns
    -------
    all_casings: Generator[`str`]
        A generator object yielding every combination of lowercase and uppercase
    """
    if not input_string:
        yield ""
    else:
        first = input_string[:1]
        if first.lower() == first.upper():
            for sub_casing in all_casings(input_string[1:]):
                yield first + sub_casing
        else:
            for sub_casing in all_casings(input_string[1:]):
                yield first.lower() + sub_casing
                yield first.upper() + sub_casing


def humanize_timedelta(
    *,
    timedelta: timedelta | None = None,
    seconds: SupportsInt | None = None,
) -> str:
    """
    Convert a `timedelta` object or time in seconds to a human-readable format

    Arguments
    ---------
    timedelta: Optional[`timedelta`]
        A `timedelta` object to convert
    seconds: Optional[`int`]
        The time in seconds

    Raises
    ------
    ValueError:
        You didn't provide either the time in seconds or a `timedelta` object to convert

    Returns
    -------
    humanize_timedelta: `str`
        The arguments in a human-readable format
    """

    try:
        obj = seconds if seconds is not None else timedelta.total_seconds()
    except AttributeError:
        raise ValueError("You must provide either a timedelta or a number of seconds")

    seconds = int(obj)
    periods = [
        ("year", "years", 60 * 60 * 24 * 365),
        ("month", "months", 60 * 60 * 24 * 30),
        ("day", "days", 60 * 60 * 24),
        ("hour", "hours", 60 * 60),
        ("minute", "minutes", 60),
        ("second", "seconds", 1),
    ]

    strings = []
    for period_name, plural_period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            if period_value == 0:
                continue
            unit = plural_period_name if period_value != 1 else period_name
            strings.append(f"{period_value} {unit}")

    return ", ".join(strings)
