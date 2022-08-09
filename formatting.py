import datetime
from typing import Generator, SupportsInt

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
    timedelta: datetime.timedelta | None = None,
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
