import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import discord
from discord import Interaction, ui
from discord.ext import commands

from bot import NotGDKID

if sys.platform == "win32":
    S = "\\"
else:
    S = "/"


class FileExporer(ui.View):
    def __init__(self, interaction: Interaction, client: NotGDKID):
        self.interaction = interaction
        self.client = client or interaction.client
        self.tree: Dict[str, List[Dict[str | Any]] | Any] = {}

        # Start building the tree
        rootdir = Path(self.client.__file__).parents[0]
        rootdir_abso = str(rootdir.absolute())
        self.tree[rootdir_abso] = []

        last_fucked_with: Path = None
        last_cwd: Path = None

        for filename in os.listdir(str(rootdir.absolute())):
            cwd: Path = rootdir
            dir_set = False

            for filename in os.listdir(str(cwd.absolute())):
                p = Path(f"{cwd.absolute()}{S}{filename}")
                self.tree[str(cwd.absolute())].append(
                    {str(p.absolute()): [] if os.path.isdir(str(p.absolute())) else 69}
                )

                if os.path.isdir(str(p.absolute())) and not dir_set and not p == last_fucked_with:
                    dir_set = True
                    cwd = p
                    last_fucked_with = p

        super().__init__(timeout=120)


class Dev(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.emoji = "<a:gdkid:868976838112841760>"

    @commands.Cog.listener()
    async def on_ready(self):
        print("Dev cog loaded")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        print(message.content)

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
