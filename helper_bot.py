from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine, Dict, List, Set, TypeVar, TYPE_CHECKING

import asyncpg
import aiohttp
import orjson
import wavelink

import discord
from discord.app_commands import AppCommandError, Choice
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
)

if TYPE_CHECKING:
    from discord import Interaction
    from discord.abc import Snowflake

    from helper_cogs.checkers import Game
    from helper_cogs.music import Music
    from utils import PostgresPool, OAuthCreds, Secrets

    KT = TypeVar("KT")
    VT = TypeVar("VT")
    Coro = Coroutine[Any, Any, None]

try:
    import uvloop  # type: ignore
except (ModuleNotFoundError, ImportError):
    pass
else:
    uvloop.install()

start = time.monotonic()
DiscordWebSocket.identify = mobile
log = logging.getLogger("NotGDKID:main")


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

    init_extensions = (*get_extensions("helper"), "utils")

    AMAZE_GUILD_ID = 996435988194791614
    ADMIN_ROLE_ID = 996437815619489922
    MEMBER_ROLE_ID = 1008572377703129119
    MUTED_ROLE_ID = 997376437390692373

    user: discord.ClientUser
    owner_ids: List[int]
    get_guild: Callable[[int], discord.Guild]
    get_channel: Callable[[int], discord.abc.Messageable]
    whitelist: Config[str | int]
    blacklist: Config[bool]
    session: aiohttp.ClientSession

    with open("config/secrets.json", "rb") as f:
        secrets: Secrets = orjson.loads(f.read())

        token = secrets["helper_token"]
        oauth_secret = secrets["helper_oauth_secret"]
        testing_token = secrets["testing_token"]
        postgres_dns = secrets["postgres_dns"] + "notgdkid"
        website_postgres = secrets["postgres_dns"] + "gdkid_xyz"
        lavalink_pass = secrets["lavalink_pass"]
        transit_id = secrets["transit_id"]
        transit_token = secrets["transit_token"]

    with open("config/spotify-creds.json", "rb") as f:
        spotify_auth: OAuthCreds = orjson.loads(f.read())

    with open("config/serverjail.json", "rb") as f:
        serverjail: Dict[str, OAuthCreds] = orjson.loads(f.read())

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
            owner_ids=[
                596481615253733408,  # gdkid
                650882112655720468,  # toilet
                1091888723060326470,  # sam
                1124467072907350026,  # little shit
            ],
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

        self.tree.interaction_check = self.tree_interaction_check
        self.tree.on_error = self.on_tree_error
        self.add_commands()

    def is_blacklisted(self, obj: Snowflake, /) -> bool:
        return obj.id in self.blacklist

    @property
    def db(self) -> PostgresPool:
        return self._db  # type: ignore

    @property
    def web_db(self) -> PostgresPool:
        return self._web_db  # type: ignore

    async def load_extension(self, name: str) -> None:
        await super().load_extension(name)

        log.info("%sloaded%s %s", PrintColours.GREEN, PrintColours.WHITE, name)

    async def unload_extension(self, name: str) -> None:
        await super().unload_extension(name)

        log.info("%sunloaded%s %s", PrintColours.RED, PrintColours.WHITE, name)

    async def reload_extension(self, name: str) -> None:
        await super().reload_extension(name)

        log.info("%sreloaded%s %s", PrintColours.YELLOW, PrintColours.WHITE, name)

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        self.whitelist = Config("dbs/whitelisted.json")
        self.blacklist = Config("dbs/blacklisted.json")
        self._db = await asyncpg.create_pool(self.postgres_dns)
        self._web_db = await asyncpg.create_pool(self.website_postgres)
        log.info("%sdatabases connected", PrintColours.GREEN)

        node = wavelink.Node(uri="http://144.172.70.155:1234", password=self.lavalink_pass)
        self.wavelink: Dict[str, wavelink.Node] = await wavelink.NodePool.connect(client=self, nodes=[node])
        log.info("%swavelink server connected", PrintColours.GREEN)

        self.status_task = status_task.start(self)
        ready_task = self.loop.create_task(self.first_ready())
        ready_task.add_done_callback(
            lambda fut: log.error("on_ready error", exc_info=e) if (e := fut.exception()) else ...
        )

        for extension in self.init_extensions:
            await self.load_extension(extension)

    async def first_ready(self):
        await self.wait_until_ready()
        log.info("%sLogged in as: %s : %d", PrintColours.PURPLE, self.user, self.user.id)

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

        await self.invoke(ctx)

    async def on_message(self, message: discord.Message):
        if message.author.bot or self.is_blacklisted(message.author):
            return

        if message.guild is not None and message.author.id not in self.owner_ids:
            if self.is_blacklisted(message.guild):
                return

            if message.guild.id in self._pending_verification:
                return

        if message.content in [f"<@!{self.user.id}>", f"<@{self.user.id}>"]:
            return await message.reply(content=message.author.mention)

        await self.process_commands(message)

    async def tree_interaction_check(self, interaction: Interaction) -> bool:
        respond: Callable[[str], Coro] = lambda msg: (
            interaction.response.autocomplete([Choice(name=msg, value="")])
            if interaction.type is discord.InteractionType.autocomplete
            else interaction.response.send_message(msg, ephemeral=True)
        )

        if self.is_blacklisted(interaction.user):
            await respond("you're blacklisted L")
            return False

        guild = interaction.guild
        if guild is not None:
            if self.is_blacklisted(guild):
                await respond("server is blacklisted")
                return False
            elif guild.id in self._pending_verification:
                await respond("server is not whitelisted")
                return False

        return True

    async def on_tree_error(self, interaction: Interaction, error: AppCommandError):
        if interaction.response.is_done():  # interaction already responded to
            return

        log.error("\n%s%s" + PrintColours.RED + traceback.format_exc())

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id in self.owner_ids and payload.emoji.name == "❌":
            try:
                msg = await self.get_channel(payload.channel_id).fetch_message(payload.message_id)

                if msg.author == self.user:
                    await msg.delete()

            except discord.HTTPException:
                pass

    async def on_guild_join(self, guild: discord.Guild):
        if self.is_blacklisted(guild):
            return await guild.leave()

        name = self.whitelist.get(guild.id)
        if name == -1:
            return await self.whitelist.put(guild.id, guild.name)

        gdkid = guild.get_member(self.owner.id)
        if not gdkid:
            await self.whitelist.remove(guild.id, missing_ok=True)
            return await guild.leave()

        self._pending_verification.add(guild.id)

        embed = Embed(
            title=f"guild joined (id - {guild.id})",
            description=f"guild name: `{guild.name}`\n\nwhitelist guild?",
            timestamp=datetime.now(tz=timezone.utc),
        )

        try:
            view = Confirm(self.owner)
            view.original_message = await gdkid.send(embed=embed, view=view)

            expired = await view.wait()
            if expired:
                return await guild.leave()

            await view.interaction.response.edit_message(view=view)
            if not view.choice:
                return await guild.leave()

            await self.whitelist.put(guild.id, guild.name)
        finally:
            self._pending_verification.discard(guild.id)

    async def on_voice_state_update(self, member: discord.Member, *_):
        vc = member.guild.voice_client
        if vc is not None:
            assert isinstance(vc, wavelink.Player) and isinstance(vc.channel, discord.VoiceChannel)

            if len(vc.channel.members) == 1:  # no one in vc besides the bot
                await vc.disconnect(force=True)

                cog: Music | None = self.get_cog("Music")  # type: ignore
                if cog and cog.loops.get(member.guild.id, None):
                    del cog.loops[member.guild.id]

                return

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
            log.info("%ssuccessfully logged out :D", PrintColours.PURPLE)

            if self._restart:
                sys.exit(69)

    async def start(self):
        await super().start(self.token)

    async def close(self, restart: bool = False):
        self._restart = restart

        with open("config/spotify-creds.json", "wb") as f:
            f.write(orjson.dumps(self.spotify_auth, option=orjson.OPT_INDENT_2))

        with open("config/serverjail.json", "wb") as f:
            f.write(orjson.dumps(self.serverjail, option=orjson.OPT_INDENT_2))

        self.status_task.cancel()
        await self.session.close()
        await self.db.close()
        await self.web_db.close()
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
