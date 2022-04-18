import inspect
import json
import os
from pathlib import Path
import time
from typing import Any, List, Dict

import discord
from discord import ui, Interaction
from discord.app_commands import (
    command,
    describe,
    choices,
    checks,
    errors,
    Choice,
    CheckFailure,
)
from discord.ext import commands

from bot import NotGDKID


class FileExporer(ui.View):
    def __init__(self, interaction: Interaction, client: NotGDKID):
        self.interaction = interaction
        self.client = client or interaction.client
        self.tree: Dict[str, List[Dict[str, Any]] | Any] = {}
        
        # Start building the tree
        ...
        
        super().__init__(timeout=120)


class Dev(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.emoji = "<a:gdkid:868976838112841760>"

    @commands.Cog.listener()
    async def on_ready(self):
        print("Dev cog loaded")

    @commands.command(aliases=["servers"], hidden=True, brief="Get the bot's server count")
    @commands.is_owner()
    async def guilds(self, ctx: commands.Context):
        command = self.client.get_command("repl exec")
        await ctx.invoke(
            command,
            code='"".join(["\\n".join(["{0.name}: {1} members | {0.id}".format(g, len([m for m in g.members if not m.bot])) for g in client.guilds]), f"\\n\\n{len(client.guilds)} servers"])',
        )

    @commands.command(hidden=True, brief="Shut down the bot")
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        e = discord.Embed(description="👋 cya")
        await ctx.reply(embed=e)
        await self.client.close()

    @commands.command(hidden=True, brief="Restart the bot")
    @commands.is_owner()
    async def restart(self, ctx: commands.Context):
        e = discord.Embed(description="❯❯ Aight brb")
        msg = await ctx.reply(embed=e)
        with open("./config/restart.json", "w") as f:
            json.dump(
                {
                    "id": msg.id,
                    "chan_id": msg.channel.id if ctx.guild else None,
                    "now": time.monotonic(),
                },
                f,
            )

        await self.client.close(restart=True)

    @commands.command(name="hi", brief='Say "Hi" to the bot', hidden=True)
    @commands.is_owner()
    async def hi(self, ctx: commands.Context):
        await ctx.reply("hi")


async def setup(client: commands.Bot):
    await client.add_cog(Dev(client=client))
