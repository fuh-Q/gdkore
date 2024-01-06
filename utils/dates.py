from datetime import datetime, timedelta, timezone
from functools import partial
from typing import SupportsInt

from zoneinfo import ZoneInfo

from .typings import Post


def is_dst(timezone: str = "America/Toronto") -> bool:
    """
    Returns `True` if DST (daylight savings) is in effect.

    Arguments
    ---------
    timezone: `str`
        The timezone to localize to. Defaults to `America/Toronto` (Eastern Daylight).

    Returns
    -------
    is_dst: `bool`
        Whether or not DST is currently being observed.
    """

    dst = datetime.now(tz=ZoneInfo(timezone)).dst()
    assert dst

    return dst.seconds != 0


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
    time = post.get("updateTime", None) or post["creationTime"]

    parse = partial(datetime.strptime, time)
    try:
        parsed = parse("%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        parsed = parse("%Y-%m-%dT%H:%M:%SZ")

    return parsed.replace(tzinfo=timezone.utc)


def humanize_timedelta(
    *,
    delta: timedelta | None = None,
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
        obj = seconds if seconds is not None else delta.total_seconds()  # type: ignore
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
