import logging
import sys
from datetime import datetime
from typing import Generator, List

from discord.embeds import (
    Embed as DPYEmbed,
    EmbedProxy as DPYEmbedProxy
)

from .enums import PrintColours

EmbedProperty = str | DPYEmbedProxy | List[DPYEmbedProxy]

class Embed(DPYEmbed):
    def character_count(self) -> int:
        """
        Gets the combined character count of the following embed properties:
        - Author (`name`)
        - Fields (`name` + `value`)
        - Footer (`text`)
        - Description
        - Title

        Returns
        -------
        character_count: `int`
            The total number of characters displayed on the embed
        """

        def count_proxy(count: int, obj: DPYEmbedProxy):
            for k, v in obj.__dict__.items():
                if not k.startswith("_") and isinstance(v, str) and not "url" in k:
                    count += len(v)

            return count

        will_count: map[EmbedProperty] = map(lambda n: getattr(self, n, None), ( # type: ignore
            "author",
            "fields",
            "footer",
            "description",
            "title"
        ))

        count = 0
        for item in will_count:
            if item is None:
                continue

            if isinstance(item, str):
                count += len(item)
                continue

            if isinstance(item, DPYEmbedProxy):
                count = count_proxy(count, item)
                continue

            if isinstance(item, list):
                for proxy in item:
                    count = count_proxy(count, proxy)

        return count

class GClassLogging(logging.Formatter):
    """
    Custom colour formatter for GClass's logging setup.
    """

    _ = "#" if sys.platform == "win32" else "-"
    FMT = f"%Y/%{_}m/%{_}d %{_}I:%M:%S %p"
    _fmt: str

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


class cap:
    """
    Cap a string at a given size, appends an ellipsis to the end

    Usage
    -----
    ```
    really_long = "1234567890"
    print(f"{cap(really_long):5}") # 12...
    ```
    """

    def __init__(self, string: str) -> None:
        self.string = string

    def __str__(self) -> str:
        return self.string

    def __repr__(self) -> str:
        return self.string

    def __format__(self, format_spec: str) -> str:
        size = int(format_spec)
        if len(self.string) <= size:
            return self.string

        return self.string[:-3] + "..."


def all_casings(input_string: str) -> Generator[str, None, None]:
    """
    A generator that yields every combination of lowercase and uppercase in a given string.

    Arguments
    ---------
    input_string: `str`
        The string to iterate through.

    Returns
    -------
    all_casings: Generator[`str`]
        A generator object yielding every combination of lowercase and uppercase.
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
