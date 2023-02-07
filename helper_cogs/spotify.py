from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from utils import PrintColours, is_dst

import aiohttp
from discord.ext import tasks

if TYPE_CHECKING:
    from helper_bot import NotGDKID

    from utils import SpotifyCreds

session: aiohttp.ClientSession | None = None
PLAYLIST_ID = "6NHn4X5wsSpeClsptOIycY"


async def do_refresh(token: str, /) -> SpotifyCreds:
    assert session is not None
    CLIENT_ID = "38727f6c28b44b4fb9dd3e661ecba1b7"
    CLIENT_SECRET = "40d954892817442cbad09f828412c0dd"
    AUTH = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {AUTH}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with session.post(
        f"https://accounts.spotify.com/api/token?grant_type=refresh_token&refresh_token={token}",
        headers=headers,
    ) as resp:
        data: SpotifyCreds = await resp.json()
        data["refresh_token"] = token
        return data


async def try_req(token: str, /, *, logger: logging.Logger) -> aiohttp.ClientResponse:
    assert session is not None
    headers = {"Authorization": f"Bearer {token}"}

    _ = "#" if sys.platform == "win32" else "-"
    hours = -4 if is_dst() else -5
    now = datetime.now(timezone(timedelta(hours=hours)))
    data = {
        "name": now.strftime(f"%{_}I:%M %p").lower(),
        "public": True,
    }

    async with session.put(
        f"https://api.spotify.com/v1/playlists/{PLAYLIST_ID}",
        json=data,
        headers=headers,
    ) as resp:
        try:
            logger.warning(await resp.json())
        except json.JSONDecodeError:
            pass
        finally:
            return resp


@tasks.loop(minutes=1)
async def spotify_task(client: NotGDKID):
    access_token = client.spotify_auth["access_token"]
    refresh_token = client.spotify_auth["refresh_token"]

    resp = await try_req(access_token, logger=client.logger)
    colour = PrintColours.RED if resp.status >= 400 else PrintColours.GREEN
    client.logger.info("Attempt 1/2 -- Spotify responded with code: %s%d%s" % (colour, resp.status, PrintColours.WHITE))

    if resp.status == 401:
        new_creds = await do_refresh(refresh_token)
        resp = await try_req(new_creds["access_token"], logger=client.logger)
        colour = PrintColours.RED if resp.status >= 400 else PrintColours.GREEN
        client.logger.info("Attempt 2/2 -- Spotify responded with code: %s%d%s" % (colour, resp.status, PrintColours.WHITE))

        client.spotify_auth = new_creds


@spotify_task.before_loop
async def before_status_task():
    await asyncio.sleep(60 - datetime.utcnow().second)


async def teardown(_):
    spotify_task.stop()

    if session is not None and not session.closed:
        await session.close()


async def setup(client: NotGDKID):
    global session
    session = aiohttp.ClientSession()

    spotify_task.start(client)
