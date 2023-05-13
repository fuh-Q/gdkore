from __future__ import annotations

import asyncio
import base64
import random
import sys
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import TYPE_CHECKING, Any, Coroutine, Dict, Generator, List, TypeVar
from urllib.parse import quote

from utils import PrintColours, is_dst

from discord.ext import commands, tasks

if TYPE_CHECKING:
    from helper_bot import NotGDKID
    from utils import OAuthCreds, NGKContext, Tracks

    T = TypeVar("T")
    Response = Coroutine[Any, Any, T]

PLAYLIST_ID = "6NHn4X5wsSpeClsptOIycY"
CLIENT_ID = "38727f6c28b44b4fb9dd3e661ecba1b7"
CLIENT_SECRET = "40d954892817442cbad09f828412c0dd"


class Route:
    BASE = "https://api.spotify.com/v1"

    def __init__(self, method: str, endpoint: str, /, **kwargs: Any):
        self.method = method
        self.endpoint = endpoint
        self.url = self.BASE + endpoint.format_map({k: quote(str(v)) for k, v in kwargs.items()})

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.method} {self.endpoint}'>"


class Spotify(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client
        self.session = client.session
        self.logger = client.logger
        self.creds = client.spotify_auth

    async def cog_load(self):
        self.spotify_task = tasks.loop(minutes=1)(self.update_name)
        self.spotify_task.before_loop(partial(asyncio.sleep, 60 - datetime.utcnow().second))
        self.spotify_task.start()

    async def cog_unload(self):
        self.spotify_task.stop()

    @staticmethod
    def partition(iterable: List[T], /, *, size: int) -> Generator[List[T], Any, Any]:
        return (iterable[i : i + size] for i in range(0, len(iterable), size))

    async def do_refresh(self) -> OAuthCreds:
        AUTH = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        token = self.creds["refresh_token"]
        headers = {
            "Authorization": f"Basic {AUTH}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with self.session.post(
            f"https://accounts.spotify.com/api/token?grant_type=refresh_token&refresh_token={token}",
            headers=headers,
        ) as resp:
            colour = PrintColours.RED if resp.status >= 400 else PrintColours.GREEN
            self.logger.info(
                "Refreshing access token... Spotify responded with: %s%d%s" % (colour, resp.status, PrintColours.WHITE)
            )

            data: OAuthCreds = await resp.json()
            data["refresh_token"] = token
            return data

    async def request(
        self,
        route: Route,
        /,
        *,
        content_type: str = "application/json",
        data: Dict[str, Any] | None = None,
        json: Dict[str, Any] | None = None,
        **params: Any,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self.creds['access_token']}", "Content-Type": content_type}
        if params:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            route.url = route.url + "?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())

        for tries in range(5):
            async with self.session.request(
                route.method,
                route.url,
                data=data,
                json=json,
                headers=headers,
            ) as resp:
                colour = PrintColours.RED if resp.status >= 400 else PrintColours.GREEN
                self.client.logger.info(
                    "Att %d/5 %s -- Spotify responded with: %s%d%s"
                    % (tries + 1, route.endpoint, colour, resp.status, PrintColours.WHITE)
                )

                try:
                    response_body = await resp.json()
                except:
                    response_body = await resp.text()

                if resp.status >= 400:
                    self.logger.warning(response_body)

                if resp.status == 401:
                    new_creds = await self.do_refresh()
                    headers["Authorization"] = new_creds["access_token"]
                    self.client.spotify_auth = self.creds = new_creds
                    continue

                if resp.status == 429:
                    retry_after = resp.headers["Retry-After"]
                    self.logger.warning(
                        "Spotify ratelimit hit for %s %s, waiting %ss" % (route.method, route.endpoint, retry_after)
                    )

                    await asyncio.sleep(float(retry_after))
                    continue

                if resp.status >= 500:
                    await asyncio.sleep(1 + tries * 2)
                    continue

                return response_body

    async def update_name(self) -> Response[None]:
        _ = "#" if sys.platform == "win32" else "-"
        hours = -4 if is_dst() else -5
        now = datetime.now(timezone(timedelta(hours=hours)))
        data = {
            "name": now.strftime(f"%{_}I:%M %p").lower(),
            "public": True,
        }

        return await self.request(Route("PUT", "/playlists/{playlist_id}", playlist_id=PLAYLIST_ID), json=data)

    def get_tracks(self, *, offset: int = 0) -> Response[Tracks]:
        r = Route("GET", "/playlists/{playlist_id}/tracks", playlist_id=PLAYLIST_ID)
        return self.request(r, fields="total,next,items(track(uri))", limit=100, offset=offset)

    def update_tracks(self, *, tracks: List[str]) -> Response[None]:
        r = Route("PUT", "/playlists/{playlist_id}/tracks", playlist_id=PLAYLIST_ID)
        payload = {"uris": tracks}
        return self.request(r, json=payload)

    @commands.command(name="shuffletracks", aliases=["shuffle", "ss"])
    @commands.is_owner()
    async def _shuffletracks(self, ctx: NGKContext):
        def get_uris(tracks: Tracks, /) -> List[str]:
            return [i["track"]["uri"] for i in tracks["items"]]

        msg = await ctx.reply("fetching tracks...")

        payload = await self.get_tracks()
        total = payload["total"]
        tracks = get_uris(payload)
        if payload["next"]:
            for i in range(100, total, 100):
                await msg.edit(content=f"fetching tracks... ({i}-{min(i+100, total)} of {total})")
                resp = await self.get_tracks(offset=i)
                tracks += get_uris(resp)

                await asyncio.sleep(0.5)

        await msg.edit(content="shuffling...")
        random.shuffle(tracks)
        await self.update_tracks(tracks=tracks)

        await msg.edit(content="done")


async def setup(client: NotGDKID):
    await client.add_cog(Spotify(client=client))
