import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from PIL import ImageFont
from typing import Any, Dict, Mapping, Set

import asyncpg
import discord
from discord import Interaction
from discord.gateway import DiscordWebSocket
from discord.app_commands import Command, AppCommandError
from discord.ext import commands
from fuzzy_match import match
from topgg.webhook import WebhookManager
from cogs.mazes import Game, StopModes

from utils import mobile, new_call_soon, BotColours, db_init, BotEmojis, PrintColours

with open("config/secrets.json", "r") as f:
    secrets: Dict[str, str] = json.load(f)


start = time.monotonic()

asyncio.BaseEventLoop.call_soon = new_call_soon

DiscordWebSocket.identify = mobile


logging.basicConfig(level=logging.INFO)


class Amaze(commands.Bot):
    """
    The sexiest bot of all time.
    """

    __file__ = __file__
    
    logger = logging.getLogger(os.path.basename(__file__)[:-3].title())

    token = secrets["token"]
    testing_token = secrets["testing_token"]
    postgres_dns = secrets["postgres_dns"]
    topgg_auth = secrets["topgg_auth"]
    topgg_wh: WebhookManager
    
    maze_font = ImageFont.truetype("assets/Kiona-Regular.ttf", size=30)

    def __init__(self):
        allowed_mentions = discord.AllowedMentions.all()
        intents = discord.Intents.all()
        intents.presences = False
        #if sys.platform != "win32":
        #    intents.message_content = False

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
            "cogs.debug",
            "cogs.dev",
            "cogs.Eval",
            "cogs.inventory",
            "cogs.mazes",
            "cogs.mazeconfig",
            "cogs.misc",
            "cogs.voting",
            "utils",
        ]

        self.description = self.__doc__
        self.uptime = datetime.utcnow().astimezone(timezone(timedelta(hours=-4)))
        self.guild_limit = []
        self._restart = False
        
        self._mazes: Mapping[int, Game] = {}

        self.tree.on_error = self.on_app_command_error
        self.add_commands()

    @property
    def app_commands(self) -> Set[Command[Any, ..., Any]]:
        """
        Set[:class:`.Command`]: A set of application commands registered to this bot

        NOTE: This does not include :class:`.Group` objects, only their subcommands are listed
        """
        cmds = {c for c in self.tree.walk_commands()}

        return cmds
    
    async def load_extension(self, name: str) -> None:
        await super().load_extension(name)
        
        self.logger.info(
            f"{PrintColours.GREEN} loaded {PrintColours.WHITE}{name}"
        )
    
    async def unload_extension(self, name: str) -> None:
        await super().unload_extension(name)
        
        self.logger.info(
            f"{PrintColours.RED} unloaded {PrintColours.WHITE}{name}"
        )
    
    async def reload_extension(self, name: str) -> None:
        await super().reload_extension(name)
        
        self.logger.info(
            f"{PrintColours.YELLOW} reloaded {PrintColours.WHITE}{name}"
        )

    async def setup_hook(self) -> None:
        self.db = await asyncpg.create_pool(self.postgres_dns, init=db_init)
        self.logger.info(f"{PrintColours.GREEN} Database connected {PrintColours.WHITE}")

        self.loop.create_task(self.first_ready()).add_done_callback(
            lambda exc: self.logger.error(
                f"\n{PrintColours.RED}" + "".join(traceback.format_exc()) + PrintColours.WHITE
            )
            if exc.exception()
            else None
        )

        for extension in self.init_extensions:
            await self.load_extension(extension)

    async def first_ready(self):
        await self.wait_until_ready()
        self.logger.info(
            PrintColours.PURPLE + \
            f"Logged in as: {self.user.name}#{self.user.discriminator} : {self.user.id}" + \
            PrintColours.WHITE
        )

        await self.change_presence(status=discord.Status.online, activity=None)

        owner = await self.fetch_user(596481615253733408)
        self.owner = owner
        self.guild_logs = await self.fetch_webhook(992179358280196176)
        self.error_logs = await self.fetch_webhook(996132218936238172)

        end = time.monotonic()
        e = discord.Embed(description=f"❯❯  started up in ~`{round(end - start, 1)}s`")
        await owner.send(embed=e)
        
        await self.db.execute("SELECT 1") # wake it up ig
    
    async def on_guild_join(self, guild: discord.Guild):
        counter = 0
        for server in self.guilds:
            if server.owner_id == guild.owner_id:
                counter += 1
        if counter > 2:
            owner = await guild.fetch_member(guild.owner_id)
            await owner.send(
                f"I have automatically left your server [`{guild.name}`] because you've reached the limit of 2 servers owned by you with the bot. This is to encourage the \"organic growth\" needed for the bot's verification process in the future. (It's Discord's way of doing things, once the bot is verified, this limit will be removed)"
            )
            self.guild_limit.append(guild.id)
            return await guild.leave()

        e = discord.Embed(colour=BotColours.green)
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

        e = discord.Embed(colour=BotColours.red)
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
    
    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        tr = traceback.format_exc()
        self.logger.error(f"\n{tr}")
        if not interaction.response.is_done(): # already handled
            await interaction.response.send_message(
                "oopsie poopsie, an error occured\n"
                "if its an error on my end, my dev'll probably fix it soon\n"
                f"really depends on how lazy he is atm {BotEmojis.LUL}"
                f"```py\n{error}\n```",
                ephemeral=True
            )
            
            await self.error_logs.send(
                f"error in guild {interaction.guild_id}"
                f"```py\n{tr}\n```"
            )

    async def on_message(self, message: discord.Message):
        if message.content in [f"<@!{self.user.id}>", f"<@{self.user.id}>"]:
            return await message.reply(message.author.mention)

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
            self.logger.info(f"{PrintColours.PURPLE} successfully logged out :D {PrintColours.WHITE}")
            
            if self._restart:
                sys.exit(69)

    async def start(self):
        if sys.platform == "win32":
            await super().start(self.testing_token)
        else:
            await super().start(self.token)

    async def close(self, restart: bool = False):
        def runner(game: Game):
            game.disable_all()
            game.ram_cleanup()
        
        self._restart = restart
        
        length = len(self._mazes)
        self.logger.info(f" saving games...")
        failed = 0
        for index, game in enumerate(self._mazes.values()):
            await game.stop(mode=StopModes.SHUTDOWN, shutdown=True)
            await self.loop.run_in_executor(None, runner, game)
            
            message = "my developer initiated a bot shutdown, your game has been saved"
            if game.ranked:
                message += "\n\n— *points will still be counted when you load it back, sorry for the trouble*\n\u200b"
            else:
                message += "\n\u200b"            
            
            try:
                await game.original_message.edit(content=message, view=game)
            except discord.HTTPException:
                failed += 1
            
            if index != length:
                await asyncio.sleep(0.2)
        self.logger.info(f" {PrintColours.GREEN}{length}{PrintColours.WHITE} games were saved")
        self.logger.info(f" {PrintColours.RED}{failed}{PrintColours.WHITE} games failed to save")
        
        del self._mazes

        await self.db.close()
        await super().close()
    
    def add_commands(self):
        @self.command(name="load", brief="Load cogs", hidden=True)
        @commands.is_owner()
        async def _load(ctx: commands.Context, extension: str):
            the_match = match.extractOne(extension, os.listdir("./cogs") + ["utils"])
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
                await ctx.reply(
                    content=f"Loaded `{cog_fmt}`", mention_author=True
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
                cog_fmt = f"`{cog.split('.')[1]}`"
            except IndexError:
                cog_fmt = f"`{cog}`"
            try:
                await self.unload_extension(cog)
            except commands.ExtensionNotLoaded:
                return await ctx.reply(
                    content=f"`{cog_fmt}` is not loaded", mention_author=True
                )
            else:
                await ctx.reply(
                    content=f"Unloaded `{cog_fmt}`", mention_author=True
                )

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
                return await ctx.reply(
                    content=f"Reloaded {', '.join(li)}", mention_author=True
                )
            the_match = match.extractOne(extension, self.extensions)
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
            await ctx.reply(
                content=content, mention_author=True
            )


if __name__ == "__main__":
    Amaze().run()
