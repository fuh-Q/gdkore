from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import ClassVar, Dict, List, Set, TYPE_CHECKING

import wavelink

import discord
from discord.app_commands import command, describe, guilds
from discord.ext import commands

from utils import BasePages, Embed, NGKContext, voice_connected

if TYPE_CHECKING:
    from discord.ui import Item

    from helper_bot import NotGDKID

    Interaction = discord.Interaction[NotGDKID]

log = logging.getLogger(__name__)


class QueuePages(BasePages, auto_defer=False):
    TRACKS_PER_PAGE: ClassVar[int] = 10

    def __init__(self, interaction: Interaction, tracks: wavelink.Queue):
        self._pages = []
        self._current = 0
        self._parent = False
        self._interaction = interaction

        self._tracks: List[List[wavelink.Playable]] = []

        self.tracks_to_pages(tracks=tracks)

        super().__init__(timeout=self.TIMEOUT)

    def tracks_to_pages(self, *, tracks: wavelink.Queue):
        items: List[wavelink.Playable] = [i for i in tracks]
        offset = self.current_page * self.TRACKS_PER_PAGE
        interaction = self._interaction
        assert interaction.guild

        while items != []:
            page = Embed(description="")
            page.set_author(
                name=f"current queue for {interaction.guild.name}", icon_url=getattr(interaction.guild.icon, "url", None)
            )
            self._tracks.append(bundle := items[: self.TRACKS_PER_PAGE])

            assert page.description
            page.description += "\n".join(f"{i + 1}. {v.author} - {v.title}" for i, v in enumerate(bundle, start=offset))

            self._pages.append(page)
            items = items[self.TRACKS_PER_PAGE :]

    async def after_callback(self, interaction: Interaction, item: Item):
        self.update_components()
        await interaction.response.edit_message(**self.edit_kwargs)


class Music(commands.Cog):
    INACTIVITY_TIMEOUT: ClassVar[int] = 300

    MUSIC_WHITELIST: ClassVar[Set[int]] = {
        890355226517860433,  # Stupidly Decent
        749892811905564672,  # Mod Mail Inbox
    }

    def __init__(self, client: NotGDKID):
        self.client = client

        self.loops: Dict[int, wavelink.Queue] = defaultdict(wavelink.Queue)

    def _format_seconds(self, milliseconds: float | int, /) -> str:
        time: int = round(milliseconds / 1000)

        if time >= 3600:
            return f"{time//3600}h{time%3600//60}m{time%60}s"
        elif time >= 60:
            return f"{time%3600//60}m{time%60}s"
        else:
            return str(time) + "s"

    def _get_now_playing_embed(self, vc: wavelink.Player, item: wavelink.Playable, *, get_time: bool = False) -> Embed:
        if item.title.startswith(str(item.author)):
            desc = f"[{item.title}]({item.uri})"
        else:
            desc = f"[{item.author} - {item.title}]({item.uri})"

        e = Embed(
            title=f"now playing ({self._format_seconds(item.length)})",
            description=desc,
        )

        if get_time:
            assert e.description
            percent = round(vc.position / item.length * 100 / 4)
            pre = ("=" * (percent - 1)) + "◯"
            e.description += "\n\n" + pre + ((25 - len(pre)) * "=")

            start = f"<t:{round(time.time() - (vc.position / 1000))}:R>"
            end = f"<t:{round(time.time() + ((item.length - vc.position) / 1000))}:R>"
            e.add_field(name="track started", value=start).add_field(name="track will end", value=end)

        return e

    async def _wait_for_start(self, ctx: NGKContext, vc: wavelink.Player) -> None:
        assert vc.channel and vc.guild
        guild_id = vc.guild.id
        vc_id = vc.channel.id

        try:
            await self.client.wait_for(
                "wavelink_track_start",
                timeout=self.INACTIVITY_TIMEOUT,
                check=(lambda p: p.player.channel.id == vc_id and p.player.guild.id == guild_id),
            )
        except asyncio.TimeoutError:
            await vc.disconnect(force=True)
            if guild_id in self.loops:
                del self.loops[guild_id]

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        assert player is not None

        ctx: NGKContext | None = getattr(player, "ctx", None)
        if not ctx:
            return  # we set this attribute on the play command; no reason it shouldn't be there

        try:
            next_song: wavelink.Playable = player.queue.get()
            await player.play(next_song)
            await ctx.send(embed=self._get_now_playing_embed(player, next_song))
        except wavelink.QueueEmpty:
            if not player.loop:  # type: ignore
                return await self._wait_for_start(ctx, player)

            assert ctx.guild
            player.queue = self.loops[ctx.guild.id].copy()
            try:
                next_song = player.queue.get()
            except wavelink.QueueEmpty:
                return await self._wait_for_start(ctx, player)
            else:
                await player.play(next_song)
                return await ctx.send(embed=self._get_now_playing_embed(player, next_song))
        else:
            return

    @command(name="play")
    @voice_connected(owner_bypass=True)
    @guilds(*MUSIC_WHITELIST)
    @describe(query="track to search for")
    async def play(self, interaction: Interaction, *, query: str):
        """searches and plays a song from a given query"""
        assert (
            interaction.guild
            and interaction.user
            and isinstance(interaction.user, discord.Member)
            and interaction.user.voice
            and interaction.user.voice.channel
        )

        vc = interaction.guild.voice_client or await interaction.user.voice.channel.connect(cls=wavelink.Player)
        assert isinstance(vc, wavelink.Player)

        if query.startswith("https://"):
            tracks = await wavelink.Playable.search(query)
        else:
            tracks = await wavelink.Pool.fetch_tracks(f"ytsearch:{query}")

        await interaction.response.defer()
        ctx = await NGKContext.from_interaction(interaction)

        if not tracks:
            await ctx.send("track not found")
            return await self._wait_for_start(ctx, vc)

        first = tracks[0]

        if not vc.playing:
            await vc.play(first)

        entries = [first] if isinstance(tracks, list) else tracks
        await self.loops[interaction.guild.id].put_wait(entries)
        await vc.queue.put_wait(entries)

        if not hasattr(vc, "loop"):
            vc.loop = False  # type: ignore

        if first.title.startswith(str(first.author)):
            desc = f"[{first.title}]({first.uri})"
        else:
            desc = f"[{first.author} - {first.title}]({first.uri})"

        embed = Embed(title=f"track queued ({self._format_seconds(first.length)})", description=desc)
        await ctx.send(embed=embed)

        vc.ctx = ctx  # type: ignore

    @command(name="loop")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    @describe(value="enable or disable looping")
    async def loop(self, interaction: Interaction, value: bool | None):
        """toggles looping the queue"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        vc: wavelink.Player = interaction.guild.voice_client
        send = interaction.response.send_message

        if not vc.current:
            vc.loop = False  # type: ignore
            return await send("nothing is playing rn, nothing to loop")

        if value:
            vc.loop = value  # type: ignore
        else:
            try:
                vc.loop ^= True  # type: ignore
            except AttributeError:
                vc.loop = False  # type: ignore

        await send(f"looping {'enabled' if vc.loop else 'disabled'}")  # type: ignore

    @command(name="skip")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    async def skip(self, interaction: Interaction):
        """skip the current track"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        vc: wavelink.Player = interaction.guild.voice_client
        send = interaction.response.send_message

        await vc.stop()
        await send("\N{OK HAND SIGN}\u200b")

    @command(name="np")
    @voice_connected(owner_bypass=True)
    @guilds(*MUSIC_WHITELIST)
    async def now_playing(self, interaction: Interaction):
        """get the track currently being played"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        vc: wavelink.Player = interaction.guild.voice_client
        send = interaction.response.send_message

        if not vc or not vc.playing or not vc.current:
            return await send("im not playing anything rn")

        await send(embed=self._get_now_playing_embed(vc, vc.current, get_time=True))

    @command(name="queue")
    @voice_connected(owner_bypass=True)
    @guilds(*MUSIC_WHITELIST)
    async def queue(self, interaction: Interaction):
        """display the current queue of tracks"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client

        if not vc or vc.queue.is_empty and not vc.current:
            return await send("queue is empty")

        await QueuePages(interaction, vc.queue.copy()).start()

    @command(name="remove")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    @describe(position="the position of the track on the queue")
    async def remove(self, interaction: Interaction, position: int):
        """remove a track from the queue"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client
        loop = self.loops[interaction.guild.id]

        if position < 1:
            return await send("position must be equal or greater than 1")

        if position > len(vc.queue) and not vc.loop or vc.loop and position > len(loop):  # type: ignore
            return await send(f"out of range")

        assert loop._history is not None and vc.queue._history is not None

        if vc.queue.is_empty and not loop.is_empty and vc.loop:  #  type: ignore
            del loop._history[position - 1]
        elif not vc.queue.is_empty and not vc.loop:  # type: ignore
            del loop._history[position - 1]
            del vc.queue._history[position - 1]
        elif vc.queue.is_empty:
            return await send("queue is empty")

        await send(f"track removed from queue")

    @command(name="clear")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    async def clear(self, interaction: Interaction):
        """clears the queue"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client

        vc.queue.clear()
        self.loops[interaction.guild.id].clear()
        await send("queue cleared")

    @command(name="seek")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    @describe(timecode="format - 4:20 (min:sec)")
    async def seek(self, interaction: Interaction, timecode: str):
        """jump to a given position in the track"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client

        parsed = timecode.split(":")
        if len(parsed) != 2 or not parsed[0].isdigit() or not parsed[1].isdigit():
            return await send("invalid timecode; correct format is `min:sec` (e.g `4:20`)", ephemeral=True)

        total_ms = int(parsed[0]) * 60 * 1000 + int(parsed[1]) * 1000

        await vc.seek(total_ms)
        await send(f"seeked to `{timecode}`")

    @command(name="pause")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    async def pause(self, interaction: Interaction):
        """pause the current track"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client

        await vc.pause(True)
        await send("paused")

    @command(name="resume")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    async def resume(self, interaction: Interaction):
        """resume the current track"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client

        await vc.pause(False)
        await send("resumed")

    @command(name="volume")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    @describe(volume="the volume to set. range between 0-1000")
    async def volume(self, interaction: Interaction, volume: int):
        """set the volume for the player"""

        assert interaction.guild is not None and interaction.guild.voice_client is not None
        if not isinstance(interaction.guild.voice_client, wavelink.Player):
            return await interaction.response.send_message("bad voice client type")

        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client

        if volume <= 0 or volume >= 1000:
            return await send("volume must range between 0-1000", ephemeral=True)

        await vc.set_volume(volume)
        await send(f"volume set to {volume}")

    @command(name="leave")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    async def leave(self, interaction: Interaction):
        """disconnects the player from the voice channel and clears its queue"""
        assert interaction.guild and interaction.channel and interaction.guild.voice_client
        send = interaction.response.send_message

        await interaction.guild.voice_client.disconnect(force=True)
        await send("\N{OK HAND SIGN}\u200b")
        del self.loops[interaction.guild.id]


async def setup(client: NotGDKID):
    await client.add_cog(Music(client=client))
