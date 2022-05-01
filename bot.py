import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set

import discord
from discord.app_commands import Command
from discord.ext import commands, tasks
from discord.gateway import DiscordWebSocket
from fuzzy_match import match
from jishaku.shim.paginator_200 import PaginatorInterface
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

from config.utils import mobile

with open("./config/secrets.json", "r") as f:
    secrets: Dict[str, str] = json.load(f)

with open("./config/restart.json", "r") as f:
    secondary_config: Dict[str, str] = json.load(f)


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

DiscordWebSocket.identify = mobile


@tasks.loop(seconds=1)
async def status_task(client: "NotGDKID"):
    now = datetime.now(timezone(timedelta(hours=-4)))
    if now.second == 0:
        fmt = now.strftime("%I:%M")

        await client.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                name=f"the time, its {fmt[1:] if fmt[0] == '0' else fmt}", type=discord.ActivityType.watching
            ),
        )


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Bot")


class NotGDKID(commands.Bot):
    """
    The sexiest bot of all time.
    """
    
    yes = "<:checkmark:970213925637484546>"  # Checkmark
    no = "<:cross:970214651784736818>"  # X
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
            "cogs.debug",
            "cogs.dev",
            "cogs.Eval",
            "cogs.typerace",
            "cogs.utility",
            "config.utils",
        ]

        if sys.platform == "linux":
            self.init_extensions.append("cogs.tts")

        self.active_jishaku_paginators: List[PaginatorInterface] = []

        self._2048_games = []
        self._connect4_games = []

        self.cache: Dict[str, List[Dict[str, Any]]] = {}

        self.token = secrets["token"]
        self.testing_token = secrets["testing_token"]
        self.description = self.__doc__

        self.uptime = datetime.utcnow().astimezone(timezone(timedelta(hours=-4)))

        self.add_commands()

    @property
    def app_commands(self) -> Set[Command[Any, ..., Any]]:
        """
        Set[:class:`.Command`]: A set of application commands registered to this bot

        NOTE: This does not include :class:`.Group` objects, only their subcommands are listed
        """
        cmds = {c for c in self.tree.walk_commands()}

        return cmds

    async def setup_hook(self) -> None:
        cluster: MongoClient = AsyncIOMotorClient(secrets["mongoURI"], io_loop=self.loop)

        self.db = cluster["NotGDKIDDB"]

        ready_task = self.loop.create_task(self.first_ready())
        ready_task.add_done_callback(
            lambda exc: print(traceback.format_exception(e, e, e.__traceback__)) if (e := exc.exception()) else ...
        )

        for extension in self.init_extensions:
            await self.load_extension(extension)

    async def first_ready(self):
        await self.wait_until_ready()
        end = time.monotonic()
        log.info(f"Logged in as: {self.user.name} : {self.user.id}\n----- Cogs and Extensions -----\nMain bot online")

        now = datetime.now(timezone(timedelta(hours=-4)))
        fmt = now.strftime("%I:%M")

        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                name=f"the time, its {fmt[1:] if fmt[0] == '0' else fmt}", type=discord.ActivityType.watching
            ),
        )
        status_task.start(self)

        collection_names: List[str] = await self.db.list_collection_names()
        for name in collection_names:
            self.cache[name] = [d["item"] async for d in self.db[name].find()]

        if sys.platform == "linux":
            self.dweebhook = await self.fetch_webhook(954211358231130204)

        if len(secondary_config) > 0 and secondary_config["chan_id"] is not None:
            start: float = secondary_config["now"]
            restart_channel = self.get_channel(secondary_config["chan_id"])
            msg = await restart_channel.fetch_message(secondary_config["id"])

            e = msg.embeds[0].copy()
            e.description = f"❯❯  Aight brb\n" f"❯❯  k im back\n" f"❯❯  reboot took around `{round(end - start, 1)}s`"
            await msg.edit(embed=e)

            with open("./config/restart.json", "w") as f:
                json.dump({}, f)

    async def on_message(self, message: discord.Message):
        if message.content in [f"<@!{self.user.id}>", f"<@{self.user.id}>"]:
            await message.reply(content=message.author.mention)

        await self.process_commands(message)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id in self.owner_ids and payload.emoji.name == "❌":
            try:
                msg = await self.get_channel(payload.channel_id).fetch_message(payload.message_id)

                if msg.author == self.user:
                    await msg.delete()

            except discord.HTTPException:
                pass

    async def start(self):
        if str(__file__).lower() == r"d:\gdkore\bot.py":
            await super().start(self.testing_token)

        else:
            await super().start(self.token)

    async def close(self, restart: bool = False):
        if self.http.token != self.testing_token:
            for k, v in self.cache.items():
                counter = 0
                await self.db[k].delete_many({})
                for i in v:
                    await self.db[k].insert_one({"_id": counter, "item": i})

                    counter += 1

        for pag in self.active_jishaku_paginators:
            try:
                await pag.message.edit(view=None)
                self.active_jishaku_paginators.pop(self.active_jishaku_paginators.index(pag))

            except:
                continue

            if self.active_jishaku_paginators:
                await asyncio.sleep(0.25)

        for game in self._2048_games:
            game.stop(save=True)

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
                await self.unload_extension(cog)
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
                    await self.reload_extension(extension)
                    List.append(f"`{extension[5:]}`")
                return await ctx.reply(content=f"Reloaded {', '.join(List)}", mention_author=True)
            the_match = match.extractOne(extension, self.extensions)
            if the_match[1] < 0.1:
                return await ctx.reply(
                    content="Couldn't find a cog using the query given. Sorry",
                    mention_author=True,
                )
            cog = str(the_match[0])
            await self.reload_extension(cog)
            await ctx.reply(content=f"Reloaded `{cog[5:]}`", mention_author=True)


if __name__ == "__main__":
    NotGDKID().run()
