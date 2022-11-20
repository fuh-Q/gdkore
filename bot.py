from __future__ import annotations

# <-- stdlib imports -->
import asyncio
import io
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Tuple, TYPE_CHECKING

# <-- discord imports -->
import discord
from discord.gateway import DiscordWebSocket
from discord.app_commands import errors, CheckFailure
from discord.ext import commands

# <-- google imports -->
from google_auth_oauthlib.flow import Flow
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# <-- database imports -->
import asyncpg
import aiohttp
from redis import asyncio as aioredis

# <-- other imports -->
from fuzzy_match import match

# <-- local imports -->
from utils import BotColours, BotEmojis, Embed, GClassLogging, PrintColours, db_init, is_dst, mobile, new_call_soon

# <-- type checking -->
if TYPE_CHECKING:
    from types import ModuleType

    from discord import Interaction
    from discord.app_commands import AppCommandError, CommandInvokeError

    from topgg.webhook import WebhookManager

    from cogs.browser import Browser
    from utils import PostgresPool

# <-- uvloop -->
try:
    import uvloop
except (ModuleNotFoundError, ImportError):
    pass
else:
    uvloop.install()

# <-- load secrets file -->
with open("config/secrets.json", "r") as f:
    secrets: Dict[str, str] = json.load(f)

# <-- misc (too little to each deserve a section) -->
start = time.monotonic()

asyncio.BaseEventLoop.call_soon = new_call_soon
DiscordWebSocket.identify = mobile

logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)


class GClass(commands.Bot):
    """
    The sexiest bot of all time.
    """

    __file__ = __file__

    LOGIN_CMD_ID = 1034690162585763840
    LOGOUT_CMD_ID = 1034690162585763841
    SCOPES = [
        "https://www.googleapis.com/auth/classroom.announcements.readonly",
        "https://www.googleapis.com/auth/classroom.courses.readonly",
        "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
        "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    ]

    logger = logging.getLogger(__name__)

    token = secrets["token"]
    testing_token = secrets["testing_token"]
    postgres_dns = secrets["postgres_dns"] + "gclass"
    redis_dns = f"redis://{secrets['vps_ip']}"
    topgg_auth = secrets["topgg_auth"]
    topgg_wh: WebhookManager
    session: aiohttp.ClientSession

    google_flow = Flow.from_client_secrets_file("config/google-creds.json", scopes=SCOPES)
    google_flow.redirect_uri = "https://gclass.onrender.com"

    user: discord.ClientUser
    owner_ids: List[int]
    get_guild: Callable[[int], discord.Guild]
    get_channel: Callable[[int], discord.abc.Messageable]

    def __init__(self):
        allowed_mentions = discord.AllowedMentions.all()
        intents = discord.Intents.default()
        if sys.platform == "win32":
            intents.message_content = True

        super().__init__(
            command_prefix=lambda *args: commands.when_mentioned(*args),
            allowed_mentions=allowed_mentions,
            help_command=None,
            intents=intents,
            case_insensitive=True,
            chunk_guilds_at_startup=False,
            max_messages=None,
            status=discord.Status.idle,
            activity=discord.Activity(
                name="Connecting...",
                type=discord.ActivityType.playing,
            ),
            owner_ids=[596481615253733408, 650882112655720468],
        )

        os.environ["JISHAKU_HIDE"] = "True"
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
        os.environ["JISHAKU_USE_BRAILLE_J"] = "True"

        self.init_extensions = [
            "cogs.authorization",
            "cogs.browser",
            "cogs.debug",
            "cogs.dev",
            "cogs.Eval",
            "cogs.voting",
            "cogs.webhooks",
            "utils",
        ]

        self._restart = False
        self.description = self.__doc__ or ""
        self.guild_limit = []
        self.uptime = datetime.now(tz=timezone(timedelta(hours=-4 if is_dst() else -5)))

        self.tree.on_error = self.on_app_command_error
        self.add_commands()

    async def remove_access(self, user_id: int):
        """
        Revokes a user's access on both the bot's end as well as Google's end.

        Parameters
        ----------
        user_id: `int`
            The ID of the user to revoke.

        Raises
        ------
        `RuntimeError`
            The user was not found.
        """

        try:
            cog: Browser = self.get_cog("Browser")  # type: ignore
            del cog.course_cache[user_id]
        except KeyError:
            pass

        q = """DELETE FROM authorized
                WHERE user_id = $1 RETURNING expiry, credentials
            """
        data = await self.db.fetchrow(q, user_id)
        if not data:
            raise RuntimeError("Could not find user.")
        else:
            creds = Credentials.from_authorized_user_info(data["credentials"])
            creds.expiry = data["expiry"]

            names = self.table_names
            names.remove("authorized")
            for table in names:
                q = (
                    """DELETE FROM %s
                        WHERE user_id = $1
                    """
                    % table
                )
                await self.db.execute(q, user_id)

        if not creds.valid:
            await asyncio.to_thread(creds.refresh, Request())
        await self.session.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": creds.token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    @property
    def db(self) -> PostgresPool:
        return self._db  # type: ignore

    @property
    def table_names(self) -> List[str]:
        """
        List[:class:`str`] A list of names of database tables used for various features
        """

        return self._table_names.copy()

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
        self._db = await asyncpg.create_pool(self.postgres_dns, init=db_init)
        self.redis = aioredis.from_url(
            self.redis_dns,
            password=secrets["redis_password"],
            port=6379,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=60.0,
            socket_timeout=60.0,
        )
        self.logger.info(f"{PrintColours.GREEN}databases connected")

        self.loop.create_task(self.first_ready()).add_done_callback(
            lambda exc: self.logger.error(traceback.format_exc()) if exc.exception() else None
        )

        q = """SELECT tablename FROM pg_tables
                WHERE tableowner = 'GDKID'
            """
        self._table_names = [i[0] for i in await self.db.fetch(q)]
        self.avatar_bytes = await self.user.avatar.read() if self.user.avatar else b""

        for extension in self.init_extensions:
            await self.load_extension(extension)

    async def first_ready(self):
        await self.wait_until_ready()
        self.logger.info(PrintColours.PURPLE + f"logged in as: {self.user.name}#{self.user.discriminator} : {self.user.id}")

        await self.change_presence(status=discord.Status.online, activity=None)

        owner = await self.fetch_user(596481615253733408)
        self.owner = owner
        self.guild_logs = await self.fetch_webhook(992179358280196176)
        self.error_logs = await self.fetch_webhook(996132218936238172)

        end = time.monotonic()
        e = Embed(description=f"❯❯  started up in ~`{round(end - start, 1)}s`")
        await owner.send(embed=e)

        await self.db.execute("SELECT 1")  # wake it up ig

    async def on_guild_join(self, guild: discord.Guild):
        counter = 0
        for server in self.guilds:
            if server.owner_id == guild.owner_id:
                counter += 1
        if counter > 2:
            assert guild.owner_id
            owner = await guild.fetch_member(guild.owner_id)
            await owner.send(
                f"I have automatically left your server [`{guild.name}`] because you've reached the limit of 2 servers owned by you with the bot. This is to encourage the \"organic growth\" needed for the bot's verification process in the future. (It's Discord's way of doing things, once the bot is verified, this limit will be removed)"
            )
            self.guild_limit.append(guild.id)
            return await guild.leave()

        e = Embed(colour=BotColours.green)
        e.set_author(
            name=f"Guild Joined ({len(self.guilds)} servers)",
            icon_url="https://cdn.discordapp.com/emojis/816263605686894612.png?size=160",
        )
        e.add_field(name="Guild Name", value=guild.name)
        e.add_field(name="Guild ID", value=guild.id)
        e.add_field(name="Guild Member Count", value=guild.member_count)
        e.add_field(
            name="Guild Owner",
            value=f"[ <@!{guild.owner_id}> ]",
        )
        if guild.icon:
            e.set_thumbnail(url=guild.icon.url)

        await self.guild_logs.send(embed=e)

    async def on_guild_remove(self, guild: discord.Guild):
        try:
            self.guild_limit.remove(guild.id)
        except ValueError:
            pass
        else:
            return

        e = Embed(colour=BotColours.red)
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

    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError | CommandInvokeError):
        if (responded := interaction.response.is_done()) and isinstance(error, CheckFailure):
            return
        else:
            method = interaction.response.send_message if not responded else interaction.followup.send

        if hasattr(error, "original"):
            error = getattr(error, "original")

        # <-- actual error checks -->
        if isinstance(error, errors.CommandOnCooldown):
            return await method(f"this command is on cooldown, try again in `{error.retry_after:.2f}`s", ephemeral=True)
        if isinstance(error, RefreshError):
            q = """DELETE FROM authorized
                    WHERE user_id = $1
                """
            await self.db.execute(q, interaction.user.id)

        if isinstance(error, (CheckFailure, RefreshError)):
            return await method(f"you need to be logged in, you can do so with </login:{self.LOGIN_CMD_ID}>", ephemeral=True)

        # <-- send to error logs -->
        tr = traceback.format_exc()
        self.logger.error(f"\n{PrintColours.RED}{tr}")
        await method(
            "oopsie poopsie, an error occured\n"
            "if its an error on my end, my dev'll probably fix it soon\n"
            f"really depends on how lazy he is atm {BotEmojis.LUL}"
            f"```py\n{error}\n```",
            ephemeral=True,
        )

        location = f"guild {interaction.guild_id}" if interaction.guild else f"dms with <@!{interaction.user.id}>"

        await self.error_logs.send(
            f"error in {location}", file=discord.File(io.BytesIO(tr.encode("utf-8")), filename="traceback.py")
        )

    async def on_message(self, message: discord.Message):
        if message.content in [f"<@!{self.user.id}>", f"<@{self.user.id}>"]:
            return await message.reply(message.author.mention)

        await self.process_commands(message)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id in self.owner_ids and payload.emoji.name == "❌":
            try:
                msg = await self.get_channel(payload.channel_id).fetch_message(payload.message_id)

                if msg.author == self.user:
                    await msg.delete()

            except discord.HTTPException:
                pass

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
        self.session = aiohttp.ClientSession()

        if sys.platform == "win32":
            await super().start(self.testing_token)
        else:
            await super().start(self.token)

    async def close(self, restart: bool = False):
        self._restart = restart

        await self.session.close()
        await self.db.close()
        await self.redis.close()
        await super().close()

    def add_commands(self):
        @self.command(name="load", brief="Load cogs", hidden=True)
        @commands.is_owner()
        async def _load(ctx: commands.Context, extension: str):
            the_match: Tuple[str, float] = match.extractOne(extension, os.listdir("./cogs") + ["utils"])  # type: ignore

            if the_match[1] < 0.1:
                return await ctx.reply(
                    content="Couldn't find a cog using the query given. Sorry",
                    mention_author=True,
                )
            cog = "cogs." + str(the_match[0])[:-3]
            try:
                cog_fmt = f"`{cog.split('.')[1]}`"
            except IndexError:
                cog_fmt = f"`{cog}`"
            try:
                await self.load_extension(cog)
            except commands.ExtensionAlreadyLoaded:
                return await ctx.reply(
                    content=f"`{cog_fmt}` is already loaded",
                    mention_author=True,
                )
            else:
                await ctx.reply(content=f"Loaded `{cog_fmt}`", mention_author=True)

        @self.command(name="unload", brief="Unload cogs", hidden=True)
        @commands.is_owner()
        async def _unload(ctx: commands.Context, extension: str):
            the_match: Tuple[ModuleType, float] = match.extractOne(extension, self.extensions)  # type: ignore

            if the_match[1] < 0.1:
                return await ctx.reply(
                    content="Couldn't find a cog using the query given. Sorry",
                    mention_author=True,
                )
            cog = str(the_match[0])
            try:
                cog_fmt = f"`{cog.split('.')[1]}`"
            except IndexError:
                cog_fmt = f"`{cog}`"
            try:
                await self.unload_extension(cog)
            except commands.ExtensionNotLoaded:
                return await ctx.reply(content=f"`{cog_fmt}` is not loaded", mention_author=True)
            else:
                await ctx.reply(content=f"Unloaded `{cog_fmt}`", mention_author=True)

        @self.command(name="reload", brief="Reload cogs", hidden=True)
        @commands.is_owner()
        async def _reload(ctx: commands.Context, extension: str):
            if extension.lower() in ["all", "~", "."]:
                li = []
                for extension in list(self.extensions):
                    await self.reload_extension(extension)
                    try:
                        li.append(f"`{extension.split('.')[1]}`")
                    except IndexError:
                        li.append(f"`{extension}`")
                return await ctx.reply(content=f"Reloaded {', '.join(li)}", mention_author=True)
            the_match: Tuple[ModuleType, float] = match.extractOne(extension, self.extensions)  # type: ignore

            if the_match[1] < 0.1:
                return await ctx.reply(
                    content="Couldn't find a cog using the query given. Sorry",
                    mention_author=True,
                )
            cog = str(the_match[0])
            await self.reload_extension(cog)
            try:
                content = f"Reloaded `{cog.split('.')[1]}`"
            except IndexError:
                content = f"Reloaded `{cog}`"
            await ctx.reply(content=content, mention_author=True)


if __name__ == "__main__":
    GClass().run()
