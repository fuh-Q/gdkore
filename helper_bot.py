import asyncio
import io
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Set

import asyncpg
import discord
from discord.gateway import DiscordWebSocket
from discord.app_commands import Command
from discord.ext import commands
from fuzzy_match import match

from utils import mobile, new_call_soon

with open("config/secrets.json", "r") as f:
    secrets: Dict[str, str] = json.load(f)


start = time.monotonic()

asyncio.BaseEventLoop.call_soon = new_call_soon

DiscordWebSocket.identify = mobile


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Bot")


class NotGDKID(commands.Bot):
    """
    The sexiest bot of all time.
    """

    __file__ = __file__
    
    AMAZE_GUILD_ID = 996435988194791614
    ADMIN_ROLE_ID = 996437815619489922
    MEMBER_ROLE_ID = 1008572377703129119
    MUTED_ROLE_ID = 997376437390692373
    
    WHITELISTED_GUILDS = [
        716684586129817651, # GDK1D's Discord
        749892811905564672, # Mod Mail Inbox
        956041825129496586, # not gdkid
        764592577575911434, # Vector Development
        890355226517860433, # Stupidly Decent
        996435988194791614, # Amaze Discord
    ]

    token = secrets["helper_token"]
    testing_token = secrets["testing_token"]
    postgres_dns = secrets["postgres_dns"]

    def __init__(self):
        allowed_mentions = discord.AllowedMentions.all()
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(
            command_prefix=lambda *args: commands.when_mentioned(*args),
            allowed_mentions=allowed_mentions,
            intents=intents,
            case_insensitive=True,
            status=discord.Status.idle,
            activity=discord.Activity(
                name="Connecting...",
                type=discord.ActivityType.watching,
            ),
            owner_ids=[596481615253733408, 650882112655720468],
        )

        os.environ["JISHAKU_HIDE"] = "True"
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
        os.environ["JISHAKU_USE_BRAILLE_J"] = "True"

        self.init_extensions = [
            "cogs.debug",
            "cogs.dev",
            "cogs.Eval",
            "helper_cogs.autorole",
            "helper_cogs.bcancer",
            "helper_cogs.emojis",
            "utils",
        ]

        self.description = self.__doc__
        self.uptime = datetime.utcnow().astimezone(timezone(timedelta(hours=-4)))
        self._restart = False

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
        self.db = await asyncpg.create_pool(self.postgres_dns)

        ready_task = self.loop.create_task(self.first_ready())
        ready_task.add_done_callback(
            lambda exc: print(
                "".join(traceback.format_exception(e, e, e.__traceback__))
            )
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

        await self.change_presence(status=discord.Status.idle, activity=None)

        owner = await self.fetch_user(596481615253733408)
        self.owner = owner

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
        if guild.id not in self.WHITELISTED_GUILDS:
            await guild.leave()
    
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
        finally:
            if self._restart:
                sys.exit(69)

    async def start(self):
        if sys.platform == "win32":
            await super().start(self.testing_token)
        else:
            await super().start(self.token)

    async def close(self, restart: bool = False):
        self._restart = restart
        
        await self.db.close()
        await super().close()

    def add_commands(self):
        @self.command(name="load", brief="Load cogs", hidden=True)
        @commands.is_owner()
        async def _load(ctx: commands.Context, extension: str):
            try:
                await self.load_extension(extension)
                await ctx.reply(f"Loaded `{extension}`")
            except Exception as e:
                await ctx.reply(f"error\n```py\n{e}\n```")

        @self.command(name="unload", brief="Unload cogs", hidden=True)
        @commands.is_owner()
        async def _unload(ctx: commands.Context, extension: str):
            try:
                await self.unload_extension(extension)
                await ctx.reply(f"Unloaded `{extension}`")
            except Exception as e:
                await ctx.reply(f"error\n```py\n{e}\n```")

        @self.command(name="reload", brief="Reload cogs", hidden=True)
        @commands.is_owner()
        async def _reload(ctx: commands.Context, extension: str):
            try:
                await self.reload_extension(extension)
                await ctx.reply(f"Reloaded `{extension}`")
            except Exception as e:
                await ctx.reply(f"error\n```py\n{e}\n```")


if __name__ == "__main__":
    NotGDKID().run()