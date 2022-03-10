import asyncio
import datetime
import logging
import os
import sys
import time
import traceback
from typing import Dict

import discord
from discord.ext import commands
from discord.gateway import DiscordWebSocket
from fuzzy_match import match
from jishaku.shim.paginator_200 import PaginatorInterface

from config.json import Json

secrets: Dict[str, str] = Json.read_json("secrets")
secondary_config: Dict[str, str] = Json.read_json("restart")


def new_call_soon(self: asyncio.BaseEventLoop, callback, *args, context=None):
    if not self._closed:
        if self._debug:
            self._check_thread()
            self._check_callback(callback, "call_soon")
        handle = self._call_soon(callback, args, context)
        if handle._source_traceback:
            del handle._source_traceback[-1]
        return handle


asyncio.BaseEventLoop.call_soon = new_call_soon


async def mobile(self: DiscordWebSocket):
    payload = {
        "op": self.IDENTIFY,
        "d": {
            "token": self.token,
            "properties": {
                "$os": sys.platform,
                "$browser": "Discord iOS",
                "$device": "pycord",
                "$referrer": "",
                "$referring_domain": "",
            },
            "compress": True,
            "large_threshold": 250,
            "v": 3,
        },
    }

    if self.shard_id is not None and self.shard_count is not None:
        payload["d"]["shard"] = [self.shard_id, self.shard_count]

    state = self._connection
    if state._activity is not None or state._status is not None:
        payload["d"]["presence"] = {"status": state._status, "game": state._activity, "since": 0, "afk": False}

    if state._intents is not None:
        payload["d"]["intents"] = state._intents.value

    await self.call_hooks("before_identify", self.shard_id, initial=self._initial_identify)
    await self.send_as_json(payload)


DiscordWebSocket.identify = mobile

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Bot")


class NotGDKID(commands.Bot):
    def __init__(self):
        allowed_mentions = discord.AllowedMentions.all()
        intents = discord.Intents.all()
        intents.presences = False
        intents.message_content = False

        super().__init__(
            command_prefix=["<@!859104775429947432> ", "<@859104775429947432> "],
            allowed_mentions=allowed_mentions,
            intents=intents,
            case_insensitive=True,
        )

        os.environ["JISHAKU_HIDE"] = "True"
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
        os.environ["JISHAKU_USE_BRAILLE_J"] = "True"

        extensions = ["cogs.2048", "cogs.debug", "cogs.dev", "cogs.Eval", "cogs.utility"]

        self.owner_ids = [596481615253733408, 650882112655720468]
        self.yes = "<:yes_tick:842078179833151538>"  # Checkmark
        self.no = "<:no_cross:842078253032407120>"  # X
        self.active_jishaku_paginators: list[PaginatorInterface] = []

        self.token = secrets["token"]

        self.uptime = datetime.datetime.utcnow()

        ready_task = self.loop.create_task(self.first_ready())
        ready_task.add_done_callback(
            lambda exc: (traceback.format_exception(e, e, e.__traceback__) if (e := exc.exception()) else None)
        )

        for extension in extensions:
            self.load_extension(extension)

        self.add_commands()

    async def first_ready(self):
        await self.wait_until_ready()
        log.info(f"Logged in as: {self.user.name} : {self.user.id}\n----- Cogs and Extensions -----\nMain bot online")

        await self.sync_commands()
        log.info("Finished syncing all interaction commands!")

        try:
            secondary_config["chan_id"]
            secondary_config["id"]
            secondary_config["now"]
        except Exception:
            return

        if secondary_config["chan_id"] != 0:
            start: float = secondary_config["now"]
            restart_channel = self.get_channel(secondary_config["chan_id"])
            msg = await restart_channel.fetch_message(secondary_config["id"])

            e = msg.embeds[0].copy()
            e.description = f"❯❯ Aight brb"
            e.description += f"\n❯❯ k im back"
            e.description += "\nㅤㅤ❯❯ calculating reboot time"
            await msg.edit(embed=e)
            end = time.monotonic() + 0.5
            await asyncio.sleep(0.5)
            e.description = f"❯❯  Aight brb\n" f"❯❯  k im back\n" f"❯❯  reboot took around `{round(end - start, 1)}s`"
            await msg.edit(embed=e)

            Json.clear_json("restart")

    async def on_message(self, message: discord.Message):
        if message.content in [f"<@!{self.user.id}>", f"<@{self.user.id}>"]:
            await message.reply(content=message.author.mention)

        await self.process_commands(message)

    async def on_connect(self):
        await self.change_presence(status=discord.Status.idle, activity=discord.Game(name="Connecting..."))

    async def on_ready(self):
        await self.change_presence(status=discord.Status.online, activity=discord.Game(name="Cookie Clicker"))

    async def start(self):
        await super().start(self.token)

    async def close(self, restart: bool = False):
        for pag in self.active_jishaku_paginators:
            await pag.message.edit(view=None)
            self.active_jishaku_paginators.pop(self.active_jishaku_paginators.index(pag))

            if self.active_jishaku_paginators:
                await asyncio.sleep(0.25)

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
                self.load_extension(cog)
            except commands.ExtensionAlreadyLoaded:
                return await ctx.reply(content=f"`{cog[5:]}` is already loaded", mention_author=True)
            else:
                await ctx.reply(content=f"Loaded `{cog[5:]}`", mention_author=True)

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
                self.unload_extension(cog)
            except commands.ExtensionNotLoaded:
                return await ctx.reply(content=f"`{cog[5:]}` is not loaded", mention_author=True)
            else:
                await ctx.reply(content=f"Unloaded `{cog[5:]}`", mention_author=True)

        @self.command(name="reload", brief="Reload cogs", hidden=True)
        @commands.is_owner()
        async def _reload(ctx: commands.Context, extension: str):
            if extension.lower() in ["all", "~", "."]:
                List = []
                for extension in list(self.extensions):
                    self.reload_extension(extension)
                    List.append(f"`{extension[5:]}`")
                return await ctx.reply(content=f"Reloaded {', '.join(List)}", mention_author=True)
            the_match = match.extractOne(extension, self.extensions)
            if the_match[1] < 0.1:
                return await ctx.reply(
                    content="Couldn't find a cog using the query given. Sorry",
                    mention_author=True,
                )
            cog = str(the_match[0])
            self.reload_extension(cog)
            await ctx.reply(content=f"Reloaded `{cog[5:]}`", mention_author=True)


if __name__ == "__main__":
    NotGDKID().run()
