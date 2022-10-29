import logging
import sys
from datetime import datetime
from typing import Generator

from .enums import PrintColours

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
