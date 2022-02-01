import logging
import os

import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
# <-- These don't do anything but motor doesn't have typehints -->
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from config.json import Json
from config.utils import *

secrets: dict[str, str] = Json.read_json("secrets")
logging.basicConfig(level=logging.INFO)

mongoURI = secrets["hcMongoURI"]
cluster: MongoClient = AsyncIOMotorClient(mongoURI)
db: Database = cluster["HCDB"]


class HeistingCultBot(commands.Bot):
    def __init__(self):
        allowed_mentions = discord.AllowedMentions(
            roles=True, everyone=False, users=True, replied_user=True
        )
        intents = discord.Intents.all()

        super().__init__(
            command_prefix="hc.",
            intents=intents,
            description="",
            help_command=commands.DefaultHelpCommand(),
            allowed_mentions=allowed_mentions,
            case_insensitive=True,
        )

        extensions = [
            "cogs.debug",
            "cogs.Eval",
            "cogs.dailyheist",
            "cogs.donotracker",
            "cogs.pointtracker",
            "cogs.pingthing",
            "cogs.misc",
            "cogs.help",
        ]

        os.environ["JISHAKU_HIDE"] = "True"
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
        os.environ["JISHAKU_USE_BRAILLE_J"] = "True"
        os.environ["BOT_RESTART"] = "False"

        self.owner_ids = [596481615253733408]
        self._BotBase__cogs = (
            commands.core._CaseInsensitiveDict()
        )  # Case insensitive cogs in the help command
        self.token = secrets["hc_token"]
        self.main_guild_id = 831822972389294152
        self.yes = "<:yes_tick:842078179833151538>"
        self.cog_emote = NewEmote.from_name("<a:Stars:861487013891014658>")
        self.heist_points: Collection = db["HCPoints"]
        self.donos: Collection = db["Donos"]
        self.dono_channels: Collection = db["DonoChannels"]
        self.dono_roles: Collection = db["DonoRoles"]
        self.dono_logging: Collection = db["DonoLogging"]
        self.ping_channels: Collection = db["PingChannels"]
        self.ping_roles: Collection = db["PingRoles"]
        self.heist_channel = db["DailyHeistChannel"]

        for extension in extensions:
            if not extension.startswith("_"):
                try:
                    self.load_extension(extension)
                except commands.ExtensionAlreadyLoaded:
                    continue

    async def on_connect(self):
        await self.change_presence(
            status=discord.Status.idle, activity=discord.Game(name="Starting up...")
        )

    async def on_ready(self):
        print(
            f"Logged in as: {self.user.name} : {self.user.id}\n----- Cogs and Extensions -----\nMain bot online"
        )
        await self.change_presence(activity=discord.Game(name="with balls"))  # mmm yes

    async def on_message(self, message: discord.Message):
        if not message.guild:  # Too lazy to put guild_only() on every command
            return

        await self.process_commands(message)

    async def on_member_ban(
        self, guild: discord.Guild, member: Union[discord.Member, discord.User]
    ):
        if not isinstance(
            member, discord.Member
        ):  # They were banned while not in the server
            return

        await self.heist_points.delete_one({"_id": member.id})
        await self.donos.delete_one({"_id": member.id})

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(
                content="This command is on cooldown, try again in `{:.2f}` seconds".format(
                    error.retry_after
                ),
                mention_author=True,
            )
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                content=f"You are missing the required arguments for this command; the proper usage would be `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
            )

        if isinstance(error, commands.NoPrivateMessage):
            return

        if isinstance(error, commands.CheckAnyFailure):
            pass

    async def start(self, *args, **kwargs):
        await super().start(self.token, *args, **kwargs)

    async def close(self):
        await super().close()

    def add_commands(self):
        @self.command(name="load", brief="Load cogs", hidden=True)
        @commands.is_owner()
        async def _load(ctx: commands.Context, extension: str):
            self.load_extension(f"cogs.{extension}")
            await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

        @self.command(name="unload", brief="Unload cogs", hidden=True)
        @commands.is_owner()
        async def _unload(ctx: commands.Context, extension: str):
            self.unload_extension(f"cogs.{extension}")
            await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

        @self.command(name="reload", brief="Reload cogs", hidden=True)
        @commands.is_owner()
        async def _reload(ctx: commands.Context, extension: str):
            self.reload_extension(f"cogs.{extension}")
            await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")


if __name__ == "__main__":
    HeistingCultBot().run()
