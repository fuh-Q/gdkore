from datetime import datetime, timezone
from functools import partial

from pytz import timezone as pytimezone

from .types import Post

def is_dst():
    """
    Returns `True` if DST (daylight savings) is in effect

    Returns
    -------
    is_dst: `bool`
        Whether or not DST is currently being observed
    """
    tz = pytimezone("UTC")
    aware = tz.localize(datetime.utcnow(), is_dst=None)

    return aware.tzinfo._dst.seconds != 0 # type: ignore


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
