import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set, Type

import asyncpg
import discord
from discord.app_commands import Command
from discord.ext import commands, tasks
from discord.gateway import DiscordWebSocket
from fuzzy_match import match
from jishaku.shim.paginator_200 import PaginatorInterface

from config.utils import Botcolours, BotEmojis, mobile

with open("config/secrets.json", "r") as f:
    secrets: Dict[str, str] = json.load(f)


def new_call_soon(self: asyncio.BaseEventLoop, callback, *args, context=None):
    if not self._closed:
        if self._debug:
            self._check_thread()
            self._check_callback(callback, "call_soon")
        handle = self._call_soon(callback, args, context)
        if handle._source_traceback:
            del handle._source_traceback[-1]
        return handle


start = time.monotonic()

asyncio.BaseEventLoop.call_soon = new_call_soon

DiscordWebSocket.identify = mobile


@tasks.loop(seconds=1)
async def status_task(client: "NotGDKID"):
    now = datetime.now(timezone(timedelta(hours=-4)))
    if now.second == 0:
        fmt = now.strftime("%I:%M")

        await client.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                name=f"the time, its {fmt[1:] if fmt[0] == '0' else fmt}",
                type=discord.ActivityType.watching,
            ),
        )


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Bot")


class NotGDKID(commands.Bot):
    """
    The sexiest bot of all time.
    """

    __file__ = __file__

    def __init__(self):
        allowed_mentions = discord.AllowedMentions.all()
        intents = discord.Intents.all()
        intents.presences = False
        intents.message_content = False if sys.platform != "win32" else True

        super().__init__(
            command_prefix=[
                "<@!859104775429947432> ",
                "<@859104775429947432> ",
                "<@!865596669999054910> ",
                "<@865596669999054910> " "B!",
                "b!",
            ],
            allowed_mentions=allowed_mentions,
            intents=intents,
            case_insensitive=True,
            chunk_guilds_at_startup=False,
            status=discord.Status.idle,
            activity=discord.Game(name="Connecting..."),
            owner_ids=[596481615253733408, 650882112655720468],
        )

        os.environ["JISHAKU_HIDE"] = "True"
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
        os.environ["JISHAKU_USE_BRAILLE_J"] = "True"

        self.init_extensions = [
            "cogs.2048",
            "cogs.connect4",
            "cogs.checkers",
            "cogs.debug",
            "cogs.dev",
            "cogs.Eval",
            "cogs.howto",
            "cogs.typerace",
            "cogs.utility",
            "cogs.words",
            "config.utils",
        ]

        if sys.platform == "linux":
            self.init_extensions.append("cogs.tts")

        self.active_jishaku_paginators: List[PaginatorInterface] = []

        self._2048_games = []
        self._connect4_games = []
        self._checkers_games = []
        self._hangman_games = []

        self.token = secrets["token"]
        self.testing_token = secrets["testing_token"]
        self.postgres_dns = secrets["postgres_dns"]
        self.description = self.__doc__

        self.uptime = datetime.utcnow().astimezone(timezone(timedelta(hours=-4)))

        self.add_commands()

    @property
    def emotes(self) -> Type[BotEmojis]:
        """
        Type[:class:`BotEmojis`]: The string format of emojis used on this bot
        """
        return BotEmojis

    @property
    def app_commands(self) -> Set[Command[Any, ..., Any]]:
        """
        Set[:class:`.Command`]: A set of application commands registered to this bot

        NOTE: This does not include :class:`.Group` objects, only their subcommands are listed
        """
        cmds = {c for c in self.tree.walk_commands()}

        return cmds

    async def setup_hook(self) -> None:
        self.db = await asyncpg.create_pool(self.postgres_dns)

        ready_task = self.loop.create_task(self.first_ready())
        ready_task.add_done_callback(
            lambda exc: print(traceback.format_exception(e, e, e.__traceback__))
            if (e := exc.exception())
            else ...
        )

        for extension in self.init_extensions:
            await self.load_extension(extension)

    async def first_ready(self):
        await self.wait_until_ready()
        log.info(
            f"Logged in as: {self.user.name} : {self.user.id}\n----- Cogs and Extensions -----\nMain bot online"
        )

        now = datetime.now(timezone(timedelta(hours=-4)))
        fmt = now.strftime("%I:%M")

        self.guild_logs = await self.fetch_webhook(905343987555131403)
        self.status_task = status_task

        if sys.platform == "linux":
            self.dweebhook = await self.fetch_webhook(954211358231130204)

        owner = await self.fetch_user(596481615253733408)

        end = time.monotonic()
        e = discord.Embed(description=f"❯❯  started up in ~`{round(end - start, 1)}s`")
        await owner.send(embed=e)

    async def on_message(self, message: discord.Message):
        if message.content in [f"<@!{self.user.id}>", f"<@{self.user.id}>"]:
            await message.reply(content=message.author.mention)

        await self.process_commands(message)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id in self.owner_ids and payload.emoji.name == "❌":
            try:
                msg = await self.get_channel(payload.channel_id).fetch_message(
                    payload.message_id
                )

                if msg.author == self.user:
                    await msg.delete()

            except discord.HTTPException:
                pass

    async def on_guild_join(self, guild: discord.Guild):
        e = discord.Embed(colour=Botcolours.green)
        e.set_author(
            name=f"Guild Joined ({len(self.guilds)} servers)",
            icon_url="https://cdn.discordapp.com/emojis/816263605686894612.png?size=160",
        )
        e.add_field(name="Guild Name", value=guild.name)
        e.add_field(name="Guild ID", value=guild.id)
        e.add_field(name="Guild Member Count", value=guild.member_count)
        e.add_field(
            name="Guild Owner",
            value=f"<@!{guild.owner_id}>",
        )
        if guild.icon:
            e.set_thumbnail(url=guild.icon.url)

        await self.guild_logs.send(embed=e)

    async def on_guild_remove(self, guild: discord.Guild):
        e = discord.Embed(colour=Botcolours.red)
        e.set_author(
            name=f"Guild Left ({len(self.guilds)} servers)",
            icon_url="https://cdn.discordapp.com/emojis/816263605837103164.png?size=160",
        )
        e.add_field(name="Guild Name", value=guild.name)
        e.add_field(name="Guild ID", value=guild.id)
        e.add_field(name="Guild Member Count", value=guild.member_count)
        if guild.icon:
            e.set_thumbnail(url=guild.icon.url)

        await self.guild_logs.send(embed=e)

    def run(self) -> None:
        async def runner():
            async with self:
                await self.start()

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            # nothing to do here
            # `asyncio.run` handles the loop cleanup
            # and `self.start` closes all sockets and the HTTPClient instance.
            return

    async def start(self):
        if str(__file__).lower() == r"d:\gdkore\bot.py":
            await super().start(self.testing_token)

        else:
            await super().start(self.token)

    async def close(self, restart: bool = False):
        await self.db.close()

        for pag in self.active_jishaku_paginators:
            try:
                await pag.message.edit(view=None)
                self.active_jishaku_paginators.pop(
                    self.active_jishaku_paginators.index(pag)
                )

            except:
                continue

            if self.active_jishaku_paginators:
                await asyncio.sleep(0.25)

        for game in self._2048_games:
            await game.async_stop(save=True)

        if restart is True:
            for voice in self.voice_clients:
                try:
                    await voice.disconnect()

                except Exception:
                    continue

            if self.ws is not None and self.ws.open:
                await self.ws.close(code=1000)

            sys.exit(69)

        else:
            await super().close()

    def add_commands(self):
        @self.command(name="load", brief="Load cogs", hidden=True)
        @commands.is_owner()
        async def _load(ctx: commands.Context, extension: str):
            the_match = match.extractOne(extension, os.listdir("./cogs"))
            if the_match[1] < 0.1:
                return await ctx.reply(
                    content="Couldn't find a cog using the query given. Sorry",
                    mention_author=True,
                )
            cog = "cogs." + str(the_match[0])[:-3]
            try:
                await self.load_extension(cog)
            except commands.ExtensionAlreadyLoaded:
                return await ctx.reply(
                    content=f"`{cog.split('.')[1]}` is already loaded",
                    mention_author=True,
                )
            else:
                await ctx.reply(
                    content=f"Loaded `{cog.split('.')[1]}`", mention_author=True
                )

        @self.command(name="unload", brief="Unload cogs", hidden=True)
        @commands.is_owner()
        async def _unload(ctx: commands.Context, extension: str):
            the_match = match.extractOne(extension, self.extensions)
            if the_match[1] < 0.1:
                return await ctx.reply(
                    content="Couldn't find a cog using the query given. Sorry",
                    mention_author=True,
                )
            cog = str(the_match[0])
            try:
                await self.unload_extension(cog)
            except commands.ExtensionNotLoaded:
                return await ctx.reply(
                    content=f"`{cog.split('.')[1]}` is not loaded", mention_author=True
                )
            else:
                await ctx.reply(
                    content=f"Unloaded `{cog.split('.')[1]}`", mention_author=True
                )

        @self.command(name="reload", brief="Reload cogs", hidden=True)
        @commands.is_owner()
        async def _reload(ctx: commands.Context, extension: str):
            if extension.lower() in ["all", "~", "."]:
                List = []
                for extension in list(self.extensions):
                    await self.reload_extension(extension)
                    List.append(f"`{extension.split('.')[1]}`")
                return await ctx.reply(
                    content=f"Reloaded {', '.join(List)}", mention_author=True
                )
            the_match = match.extractOne(extension, self.extensions)
            if the_match[1] < 0.1:
                return await ctx.reply(
                    content="Couldn't find a cog using the query given. Sorry",
                    mention_author=True,
                )
            cog = str(the_match[0])
            await self.reload_extension(cog)
            await ctx.reply(
                content=f"Reloaded `{cog.split('.')[1]}`", mention_author=True
            )


if __name__ == "__main__":
    NotGDKID().run()
