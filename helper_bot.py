from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Set, TYPE_CHECKING

import asyncpg

import discord
from discord.app_commands import AppCommandError
from discord.gateway import DiscordWebSocket
from discord.ext import commands, tasks

from utils import (
    Config,
    Confirm,
    Embed,
    GClassLogging,
    NGKContext,
    PrintColours,
    get_extensions,
    mobile,
    is_dst,
    new_call_soon,
)

if TYPE_CHECKING:
    from discord import Interaction

    from helper_cogs.checkers import Game
    from utils import PostgresPool

try:
    import uvloop # type: ignore
except (ModuleNotFoundError, ImportError):
    pass
else:
    uvloop.install()

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

    init_extensions = (*get_extensions(), "utils")

    logger = logging.getLogger(__name__)

    AMAZE_GUILD_ID = 996435988194791614
    ADMIN_ROLE_ID = 996437815619489922
    MEMBER_ROLE_ID = 1008572377703129119
    MUTED_ROLE_ID = 997376437390692373

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

        self._checkers_games: Set[Game] = set()

        self._pending_verification: Set[int] = set()

        self._restart = False
        self.description = self.__doc__ or ""
        self.uptime = datetime.now(tz=timezone(timedelta(hours=-4 if is_dst() else -5)))

        self.tree.interaction_check = self.on_app_command
        self.tree.on_error = self.on_app_command_error
        self.add_commands()

    @property
    def db(self) -> PostgresPool:
        return self._db  # type: ignore

    async def load_extension(self, name: str) -> None:
        await super().load_extension(name)

        self.logger.info(f"{PrintColours.GREEN}loaded{PrintColours.WHITE} {name}")

    async def unload_extension(self, name: str) -> None:
        await super().unload_extension(name)

        self.logger.info(f"{PrintColours.RED}unloaded{PrintColours.WHITE} {name}")

    async def reload_extension(self, name: str) -> None:
        await super().reload_extension(name)

        self.logger.info(f"{PrintColours.YELLOW}reloaded{PrintColours.WHITE} {name}")

    async def setup_hook(self) -> None:
        self._db = await asyncpg.create_pool(self.postgres_dns)
        self.whitelist: Config[str] = Config("config/whitelisted.json")
        self.logger.info(f"{PrintColours.GREEN}database connected")

        self.status_task = status_task.start(self)
        ready_task = self.loop.create_task(self.first_ready())
        ready_task.add_done_callback(lambda exc: print(traceback.format_exc()) if exc.exception() else ...)

        for extension in self.init_extensions:
            await self.load_extension(extension)

    async def first_ready(self):
        await self.wait_until_ready()
        self.logger.info(PrintColours.PURPLE + f"logged in as: {self.user.name}#{self.user.discriminator} : {self.user.id}")

        for guild in self.guilds:
            if guild.id not in self.whitelist:
                await asyncio.sleep(0.2)
                await guild.leave()

        await self.change_presence(status=discord.Status.idle, activity=None)
        self.owner = await self.fetch_user(596481615253733408)
        self.amaze_guild = self.get_guild(self.AMAZE_GUILD_ID)

        end = time.monotonic()
        e = Embed(description=f"❯❯  started up in ~`{round(end - start, 1)}s`")
        await self.owner.send(embed=e)

    async def process_commands(self, message: discord.Message) -> None:
        ctx = await self.get_context(message, cls=NGKContext)

        if message.author.bot:
            return

        assert message.guild is not None
        if (g := message.guild) and g.id in self._pending_verification:
            return

        await self.invoke(ctx)

    async def on_app_command(self, interaction: Interaction) -> bool:
        if (g := interaction.guild) and g.id in self._pending_verification:
            await interaction.response.send_message("server is not whitelisted", ephemeral=True)

            return False
        return True  # i only really care about servers here

    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        tr = traceback.format_exc()

        self.logger.error("\n" + tr)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

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

    async def on_guild_join(self, guild: discord.Guild):
        if not (name := self.whitelist.get(guild.id, 0)):
            if name is None:
                return await self.whitelist.put(guild.id, guild.name)

        if not guild.get_member(self.owner.id):
            await self.whitelist.remove(guild.id, missing_ok=True)
            return await guild.leave()

        self._pending_verification.add(guild.id)

        embed = Embed(
            title=f"guild joined (id - {guild.id})",
            description=f"guild name: `{guild.name}`\n\nwhitelist guild?",
            timestamp=datetime.now(tz=timezone.utc),
        )

        view = Confirm(self.owner)
        view.original_message = await self.owner.send(embed=embed, view=view)

        expired = await view.wait()
        if expired:
            return await guild.leave()

        await view.interaction.response.edit_message(view=view)
        if not view.choice:
            return await guild.leave()

        await self.whitelist.put(guild.id, guild.name)
        self._pending_verification.remove(guild.id)

    async def on_voice_state_update(self, member: discord.Member, *args):
        if member.id not in self.owner_ids:
            return

        if (
            member.voice
            and not args[0].channel  # before.channel
            and member.voice.self_mute
            and not member.voice.self_deaf
            and not member.guild.voice_client
        ):
            assert member.voice and member.voice.channel
            await member.voice.channel.connect()

        elif member.guild.voice_client and (not member.voice or member.voice.self_deaf):
            await member.guild.voice_client.disconnect(force=True)

    def run(self) -> None:
        async def runner():
            async with self:
                await self.start()

        handler = logging.StreamHandler()
        formatter = GClassLogging()
        handler.setFormatter(formatter)
        discord.utils.setup_logging(handler=handler, formatter=formatter, level=logging.INFO)

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
