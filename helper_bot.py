from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, TYPE_CHECKING

import asyncpg
import discord
from discord.app_commands import AppCommandError
from discord.gateway import DiscordWebSocket
from discord.ext import commands, tasks

from utils import GClassLogging, PrintColours, mobile, is_dst, new_call_soon

if TYPE_CHECKING:
    from discord import Interaction

    from utils import PostgresPool


with open("config/secrets.json", "r") as f:
    secrets: Dict[str, str] = json.load(f)

start = time.monotonic()
asyncio.BaseEventLoop.call_soon = new_call_soon
DiscordWebSocket.identify = mobile


@tasks.loop(minutes=1)
async def status_task(client: NotGDKID):
    _ = "#" if sys.platform == "win32" else "-"
    hours, name = (-4, "EDT") if is_dst() else (-5, "EST")
    now = datetime.now(timezone(timedelta(hours=hours)))
    fmt = now.strftime(f"%{_}I:%M %p")

    await client.change_presence(
        status=discord.Status.idle,
        activity=discord.Activity(
            name=f"{name} - {fmt}",
            type=discord.ActivityType.watching,
        ),
    )

@status_task.before_loop
async def before_status_task():
    await asyncio.sleep(60 - datetime.utcnow().second)


class NotGDKID(commands.Bot):
    """
    The sexiest bot of all time.
    """

    __file__ = __file__

    logger = logging.getLogger(__name__)

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
    postgres_dns = secrets["postgres_dns"] + "notgdkid"

    user: discord.ClientUser
    owner_ids: List[int]
    get_guild: Callable[[int], discord.Guild]
    get_channel: Callable[[int], discord.abc.Messageable]

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
            "helper_cogs.misc",
            "helper_cogs.mod",
            "helper_cogs.tts",
            "utils",
        ]

        self.description = self.__doc__ or ""
        self.uptime = datetime.utcnow().astimezone(timezone(timedelta(hours=-4)))
        self._restart = False

        self.tree.on_error = self.on_app_command_error
        self.add_commands()

    @property
    def db(self) -> PostgresPool:
        return self._db # type: ignore

    async def load_extension(self, name: str) -> None:
        await super().load_extension(name)

        self.logger.info(
            f"{PrintColours.GREEN}loaded{PrintColours.WHITE} {name}"
        )

    async def unload_extension(self, name: str) -> None:
        await super().unload_extension(name)

        self.logger.info(
            f"{PrintColours.RED}unloaded{PrintColours.WHITE} {name}"
        )

    async def reload_extension(self, name: str) -> None:
        await super().reload_extension(name)

        self.logger.info(
            f"{PrintColours.YELLOW}reloaded{PrintColours.WHITE} {name}"
        )

    async def setup_hook(self) -> None:
        self._db = await asyncpg.create_pool(self.postgres_dns)
        self.logger.info(f"{PrintColours.GREEN}database connected")

        self.status_task = status_task.start(self)
        ready_task = self.loop.create_task(self.first_ready())
        ready_task.add_done_callback(
            lambda exc: print(traceback.format_exc())
            if exc.exception() else ...
        )

        for extension in self.init_extensions:
            await self.load_extension(extension)

    async def first_ready(self):
        await self.wait_until_ready()
        self.logger.info(
            PrintColours.PURPLE + \
            f"logged in as: {self.user.name}#{self.user.discriminator} : {self.user.id}"
        )

        await self.change_presence(status=discord.Status.idle, activity=None)

        owner = await self.fetch_user(596481615253733408)
        self.owner = owner

        end = time.monotonic()
        e = discord.Embed(description=f"❯❯  started up in ~`{round(end - start, 1)}s`")
        await owner.send(embed=e)

    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        tr = traceback.format_exc()

        self.logger.error("\n" + tr)

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

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        if member.id not in self.owner_ids:
            return

        if (
            after.channel
            and after.mute
            and not member.guild.voice_client
        ):
            assert member.voice and member.voice.channel
            await member.voice.channel.connect()

        elif not member.voice and member.guild.voice_client:
            await member.guild.voice_client.disconnect(force=True)

    def run(self) -> None:
        async def runner():
            async with self:
                await self.start()

        handler = logging.StreamHandler()
        formatter = GClassLogging()
        handler.setFormatter(formatter)
        discord.utils.setup_logging(
            handler=handler,
            formatter=formatter,
            level=logging.INFO
        )

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            # nothing to do here
            # `asyncio.run` handles the loop cleanup
            # and `self.start` closes all sockets and the HTTPClient instance.
            return
        finally:
            self.logger.info(f"{PrintColours.PURPLE}successfully logged out :D")

            if self._restart:
                sys.exit(69)

    async def start(self):
        await super().start(self.token)

    async def close(self, restart: bool = False):
        self._restart = restart

        self.status_task.cancel()
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