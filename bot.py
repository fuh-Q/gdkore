import asyncio
import datetime
import logging
import os
import random
import sys
import time

import discord
from discord import ApplicationContext
from discord.ext import commands
from fuzzy_match import match
from jishaku.shim.paginator_200 import PaginatorInterface
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from config.json import Json
from config.utils import *

secrets: dict[str, str] = Json.read_json("secrets")
secondary_config: dict[str, str] = Json.read_json("restart")
mongoURI = secrets["mongoURI"]

cluster: MongoClient = AsyncIOMotorClient(mongoURI)
db: Database = cluster["BanDB"]


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


async def get_prefix(client: commands.Bot, message: discord.Message) -> list:

    if client.user.id != 865596669999054910:  # Fixed prefix on the testing bot
        if not message.guild:  # DMs
            prefixes = list(all_casings("b!"))

        else:  # Not DMs
            data = await db["BanPrefixes"].find_one(message.guild.id)

            if not data:  # No custom prefix found
                prefixes = list(all_casings("b!"))
            else:
                prefixes = list(all_casings(data["prefix"]))
    else:
        prefixes = list(all_casings("b?"))

    prefixes.append(f"<@!{client.user.id}> ")
    prefixes.append(f"<@{client.user.id}> ")

    return prefixes


logging.basicConfig(level=logging.INFO)

log = logging.getLogger("Bot")


class BanBattler(commands.Bot):

    """The ultimate ban battle bot itself"""

    def __init__(self):

        allowed_mentions = discord.AllowedMentions(roles=True, everyone=False, users=True, replied_user=True)
        intents = discord.Intents.all()
        intents.presences = False

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            allowed_mentions=allowed_mentions,
            help_command=None,
            case_insensitive=True,
        )

        extensions = [
            "cogs.banbattle",
            "cogs.debug",
            "cogs.dev",
            "cogs.Eval",
            "cogs.utility",
        ]

        os.environ["JISHAKU_HIDE"] = "True"
        os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
        os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
        os.environ["JISHAKU_USE_BRAILLE_J"] = "True"

        self.owner_ids = [596481615253733408]  # My main
        self.test_account_id = 650882112655720468  # My alt

        self.stream_url = "https://www.youtube.com/watch?v=Cjs6Ea8pbzI"  # YouTube video
        self.yes = "<:yes_tick:842078179833151538>"  # Checkmark
        self.no = "<:no_cross:842078253032407120>"  # X
        self.token = secrets["token"]  # Ban Battler's token
        self.testing_token = secrets["testing_token"]  # Ban Battler Testing's token
        self.uptime = datetime.datetime.utcnow()  # Startup timestamp
        self.color = 0x09DFFF  # Main color
        self.pfp_colour = "original"  # Pfp color
        self.guild_limit = []  # Something
        self.active_paginators: list[discord.InteractionMessage] = []
        self.active_jishaku_paginators: list[PaginatorInterface] = []

        self.prefixes: Collection = db["BanPrefixes"]
        self.blacklists: Collection = db["BanBlacklists"]
        self.guild_blacklists: Collection = db["BanGuildBlacklists"]
        self.pingrole: Collection = db["BanPing"]
        self.games: Collection = db["BanGames"]
        self.time_to_join: Collection = db["BanJoinTime"]
        self.game_timeout: Collection = db["BanTimeout"]
        self.game_emoji: Collection = db["BanEmoji"]
        self.ban_gamer: Collection = db["BanGamerRole"]
        self.starter: Collection = db["BanStarter"]
        self.self_ban_chance: Collection = db["BanYourself"]
        self.ban_dm: Collection = db["BanDM"]
        self.self_ban_dm: Collection = db["BanYourselfDM"]

        self.add_commands()

        for extension in extensions:
            if not extension.startswith("_"):
                self.load_extension(extension)

        if sys.platform != "win32":
            self.loop.create_task(self.change_avatar())

    async def process_application_commands(self, interaction: discord.Interaction):
        is_bl = await self.blacklists.find_one({"_id": interaction.user.id})
        if is_bl:
            return

        await super().process_application_commands(interaction)

    async def process_commands(self, message: discord.Message):
        ctx = await self.get_context(message)
        if message.author.bot:
            return

        if message.guild:
            is_gbl = await self.guild_blacklists.find_one({"_id": message.guild.id})
            if is_gbl:
                await message.guild.leave()
                return

        await self.invoke(ctx)

    async def change_avatar(self):
        while True:
            await asyncio.sleep(3600)
            color = random.choice(
                [
                    "red",
                    "orange",
                    "yellow",
                    "green",
                    "aqua",
                    "original",
                    "blue",
                    "purple",
                    "pink",
                ]
            )
            self.pfp_colour = color
            with open(f"pfps/{color}.png", "rb") as image:
                f = image.read()
                b = bytearray(f)
                await self.user.edit(avatar=b)

    async def on_connect(self):
        await self.change_presence(status=discord.Status.idle, activity=discord.Game(name="Starting up..."))
        await self.sync_commands()

    async def on_ready(self):
        log.info(f"Logged in as: {self.user.name} : {self.user.id}\n----- Cogs and Extensions -----\nMain bot online")
        async for doc in self.games.find({}):
            await self.games.delete_one(doc)
        await self.change_presence(activity=discord.Streaming(name="Ban Battles", url=self.stream_url))

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

            pointer_right = "<a:right:852197523509739521>"

            e = msg.embeds[0].copy()
            e.description = f"{pointer_right} Aight brb"
            e.description += f"\n{pointer_right} k im back"
            e.description += "\n<a:loading:937145488493379614> calculating reboot time"
            await msg.edit(embed=e)
            end = time.monotonic() + 0.5
            await asyncio.sleep(0.5)
            e.description = (
                f"{pointer_right} Aight brb\n"
                f"{pointer_right} k im back\n"
                f"{pointer_right} reboot took around `{round(end - start, 1)}s`"
            )
            await msg.edit(embed=e)

            Json.clear_json("restart")

    async def on_guild_join(self, guild: discord.Guild):
        counter = 0
        for server in self.guilds:
            if server.owner_id == guild.owner_id:
                counter += 1
        if counter > 2:
            await guild.owner.send(
                f"I have automatically left your server [`{guild.name}`] because you've reached the limit of 2 servers owned by you with the bot. This is to encourage the \"organic growth\" needed for the bot's verification process in the future. (It's Discord's way of doing things, once the bot is verified, this limit will be removed)"
            )
            self.guild_limit.append(guild.id)
            return await guild.leave()

        wh: discord.Webhook = await self.fetch_webhook(905343987555131403)
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
            value=f"{guild.owner.name}#{guild.owner.discriminator} [ {guild.owner.mention} ]",
        )
        if guild.icon:
            e.set_thumbnail(url=guild.icon.url)

        await wh.send(embed=e)

    async def on_guild_remove(self, guild: discord.Guild):
        try:
            self.guild_limit.index(guild.id)
        except ValueError:
            pass
        else:
            self.guild_limit.pop(self.guild_limit.index(guild.id))
            return

        wh: discord.Webhook = await self.fetch_webhook(905343987555131403)
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

        await wh.send(embed=e)

    async def on_application_command_error(
        self,
        ctx: ApplicationContext,
        error: discord.commands.ApplicationCommandInvokeError,
    ):
        if hasattr(error, "original"):
            error = error.original

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.respond(
                content="This command is on cooldown, try again in `{:.2f}` seconds".format(error.retry_after),
                ephemeral=True,
            )
            await self.log(ctx, error.retry_after)
            return
        if isinstance(error, commands.MaxConcurrencyReached):
            await ctx.respond(
                content=f"Looks like you've reached the maximum concurrency of {ctx.command._max_concurrency.number} for this command!",
                ephemeral=True,
            )
            return
        if isinstance(error, commands.NoPrivateMessage):
            errorEmbed = discord.Embed(
                title="Uh oh stinky",
                description=f"You can't use this command in DMs",
                color=0xC0382B,
            )
            errorEmbed.set_footer(text="no u")
            await ctx.respond(embed=errorEmbed)
            return
        if isinstance(error, commands.NotOwner) or isinstance(error, commands.MessageNotFound):
            pass

        await super().on_application_command_error(ctx, error)

    async def log(self, ctx: ApplicationContext, retry_after):
        wh = await self.fetch_webhook(855438899661111297)
        embed = discord.Embed(title="Cooldown triggered", color=0xC0382B)
        embed.add_field(
            name="Name",
            value=f"Name: `{ctx.author.name}#{ctx.author.discriminator}`\nMention: {ctx.author.mention}\nUser ID: {ctx.author.id}",
            inline=False,
        )
        embed.add_field(
            name="Account created at",
            value="{0}".format(ctx.author.created_at.__format__("%A, %d %B %Y\nAt %I:%M%p")),
            inline=True,
        )
        try:
            embed.add_field(
                name="Triggered in",
                value=f"Name: `{ctx.guild.name}`\nGuild ID: {ctx.guild.id}\nGuild Member Count: {ctx.guild.member_count}",
                inline=True,
            )
        except Exception:
            embed.add_field(
                name="Triggered in",
                value=f"Name: `DMs`\nGuild ID: DMs\nGuild Member Count: DMs",
                inline=True,
            )
        if ctx.command is not None:
            embed.add_field(name="Command", value=f"`/{ctx.command.qualified_name}`", inline=False)
            embed.add_field(
                name="Time left on cooldown",
                value="`{:.2f}` seconds".format(retry_after),
                inline=True,
            )
        embed.set_thumbnail(url=f"{ctx.author.avatar}")
        embed.set_footer(text="Time to ban :P", icon_url=f"{ctx.author.avatar}")
        await wh.send(
            content=f"Random number: {random.randint(10000000000, 99999999999999999999)}",
            embed=embed,
        )

    async def start(self):
        if sys.platform == "win32":
            await super().start(self.testing_token)
        else:
            await super().start(self.token)

    async def close(self, restart: bool = False):
        for pag in self.active_jishaku_paginators:
            await pag.message.edit(view=None)
            self.active_jishaku_paginators.pop(self.active_jishaku_paginators.index(pag))

            if self.active_jishaku_paginators:
                await asyncio.sleep(0.25)

        for pag in self.active_paginators:
            await pag.edit(view=None)
            self.active_paginators.pop(self.active_paginators.index(pag))

            if self.active_paginators:
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
    BanBattler().run()
