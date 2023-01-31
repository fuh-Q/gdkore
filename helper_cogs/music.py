from __future__ import annotations

import asyncio
import time
from typing import ClassVar, Dict, List, Set, TYPE_CHECKING

import wavelink

import discord
from discord.app_commands import command, describe, guilds
from discord.ext import commands

from utils import BasePages, Embed, NGKContext, voice_connected

if TYPE_CHECKING:
    from discord import Interaction
    from discord.ui import Item

    from helper_bot import NotGDKID


class QueuePages(BasePages):
    TRACKS_PER_PAGE = 10

    def __init__(self, interaction: Interaction, tracks: wavelink.WaitQueue):
        self._pages = []
        self._current = 0
        self._parent = False
        self._interaction = interaction

        self._tracks: List[List[wavelink.YouTubeTrack]] = []

        self.tracks_to_pages(tracks=tracks)

        super().__init__(timeout=self.TIMEOUT)

    def tracks_to_pages(self, *, tracks: wavelink.WaitQueue):
        items: List[wavelink.YouTubeTrack] = [i for i in tracks]  # type: ignore
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
        await self._interaction.response.edit_message(**self.edit_kwargs)


class Music(commands.Cog):
    INACTIVITY_TIMEOUT: ClassVar[int] = 300

    MUSIC_WHITELIST: ClassVar[Set[int]] = {
        890355226517860433,  # Stupidly Decent
        749892811905564672,  # Mod Mail Inbox
    }

    def __init__(self, client: NotGDKID):
        self.client = client

        self.loops: Dict[int, wavelink.WaitQueue] = {}

    def _format_seconds(self, seconds: float | int, /) -> str:
        time: int = round(seconds)

        if time >= 3600:
            return f"{time//3600}h{time%3600//60}m{time%60}s"
        elif time >= 60:
            return f"{time%3600//60}m{time%60}s"
        else:
            return str(time) + "s"

    def _get_now_playing_embed(self, vc: wavelink.Player, item: wavelink.YouTubeTrack, *, get_time: bool = False) -> Embed:
        if item.title.startswith(str(item.author)):
            desc = f"[{item.title}]({item.uri})"
        else:
            desc = f"[{item.author} - {item.title}]({item.uri})"

        e = Embed(
            title=f"now playing ({self._format_seconds(item.duration)})",
            description=desc,
        )

        if get_time:
            assert e.description
            percent = round(vc.position / item.duration * 100 / 4)
            pre = ("=" * (percent - 1)) + "◯"
            e.description += "\n\n" + pre + ((25 - len(pre)) * "=")

            start = f"<t:{round(time.time() - vc.position)}:R>"
            end = f"<t:{round(time.time() + (item.duration - vc.position))}:R>"
            e.add_field(name="track started", value=start).add_field(name="track will end", value=end)

        return e

    async def _wait_for_start(self, ctx: NGKContext, vc: wavelink.Player) -> None:
        try:
            await self.client.wait_for(
                "wavelink_track_start",
                timeout=self.INACTIVITY_TIMEOUT,
                check=(lambda p, t, r: p.channel.id == vc.channel.id and p.guild.id == vc.guild.id),
            )
        except asyncio.TimeoutError:
            assert ctx.guild
            await vc.disconnect(force=True)
            del self.loops[ctx.guild.id]

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.Track, reason: str):
        ctx: NGKContext = player.ctx  # type: ignore

        try:
            next_song: wavelink.YouTubeTrack = player.queue.get()  # type: ignore
            await player.play(next_song)
            await ctx.send(embed=self._get_now_playing_embed(player, next_song))
        except wavelink.QueueEmpty:
            if player.loop:  # type: ignore
                assert ctx.guild
                player.queue = self.loops[ctx.guild.id].copy()  # type: ignore
                try:
                    next_song = player.queue.get()  # type: ignore
                except wavelink.QueueEmpty:
                    return await self._wait_for_start(ctx, player)
                else:
                    await player.play(next_song)
                    return await ctx.send(embed=self._get_now_playing_embed(player, next_song))

            await self._wait_for_start(ctx, player)
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

        await interaction.response.defer()
        ctx = await NGKContext.from_interaction(interaction)
        results = await vc.node.get_tracks(wavelink.YouTubeTrack, f"ytsearch:{query}")
        if not results:
            await ctx.send("track not found")
            return await self._wait_for_start(ctx, vc)
        else:
            track = results[0]

        if vc.queue.is_empty and not vc.is_playing():
            self.loops[interaction.guild.id] = vc.queue.copy()  # type: ignore
            await vc.play(track)
            vc.loop = False  # type: ignore
        else:
            await vc.queue.put_wait(track)

        await self.loops[interaction.guild.id].put_wait(track)

        if track.title.startswith(str(track.author)):
            desc = f"[{track.title}]({track.uri})"
        else:
            desc = f"[{track.author} - {track.title}]({track.uri})"

        embed = Embed(title=f"track queued ({self._format_seconds(track.duration)})", description=desc)
        await ctx.send(embed=embed)

        vc.ctx = ctx  # type: ignore

    @command(name="loop")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    @describe(value="enable or disable looping")
    async def loop(selef, interaction: Interaction, value: bool | None):
        """toggles looping the queue"""
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
        send = interaction.response.send_message

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
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
        send = interaction.response.send_message

        await vc.stop()
        await send("\N{OK HAND SIGN}\u200b")

    @command(name="np")
    @voice_connected(owner_bypass=True)
    @guilds(*MUSIC_WHITELIST)
    async def now_playing(self, interaction: Interaction):
        """get the track currently being played"""
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
        send = interaction.response.send_message

        if not vc or not vc.is_playing() or not vc.source:
            return await send("im not playing anything rn")

        assert isinstance(vc.source, wavelink.YouTubeTrack)
        await send(embed=self._get_now_playing_embed(vc, vc.source, get_time=True))

    @command(name="queue")
    @voice_connected(owner_bypass=True)
    @guilds(*MUSIC_WHITELIST)
    async def queue(self, interaction: Interaction):
        """display the current queue of tracks"""
        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        if not vc or vc.queue.is_empty:
            return await send("queue is empty")

        if vc.queue.is_empty and not self.loops[interaction.guild.id].is_empty and vc.loop:  # type: ignore
            return await QueuePages(interaction, self.loops[interaction.guild.id].copy()).start()  # type: ignore

        await QueuePages(interaction, vc.queue.copy()).start()  # type: ignore

    @command(name="remove")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    @describe(position="the position of the track on the queue")
    async def remove(self, interaction: Interaction, position: int):
        """remove a track from the queue"""
        assert interaction.guild
        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore
        loop = self.loops[interaction.guild.id]

        if position < 1:
            return await send("position must be equal or greater than 1")

        if position > len(vc.queue) and not vc.loop or vc.loop and position > len(loop):  # type: ignore
            return await send(f"out of range")

        if vc.queue.is_empty and not loop.is_empty and vc.loop:  #  type: ignore
            del loop._queue[position - 1]
        elif not vc.queue.is_empty and not vc.loop:  # type: ignore
            del loop._queue[position - 1]
            del vc.queue._queue[position - 1]
        elif vc.queue.is_empty:
            return await send("queue is empty")

        await send(f"track removed from queue")

    @command(name="clear")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    async def clear(self, interaction: Interaction):
        """clears the queue"""
        assert interaction.guild
        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        vc.queue.clear()
        self.loops[interaction.guild.id].clear()
        await send("queue cleared")

    @command(name="seek")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    @describe(timecode="format - 4:20 (min:sec)")
    async def seek(self, interaction: Interaction, timecode: str):
        """jump to a given position in the track"""
        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

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
        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        await vc.pause()
        await send("paused")

    @command(name="resume")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    async def resume(self, interaction: Interaction):
        """resume the current track"""
        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

        await vc.resume()
        await send("resumed")

    @command(name="volume")
    @voice_connected()
    @guilds(*MUSIC_WHITELIST)
    @describe(volume="the volume to set. range between 0-1000")
    async def volume(self, interaction: Interaction, volume: int):
        """set the volume for the player"""
        send = interaction.response.send_message
        vc: wavelink.Player = interaction.guild.voice_client  # type: ignore

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
