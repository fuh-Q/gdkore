from __future__ import annotations

import discord
from discord.ext import commands

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from helper_bot import NotGDKID


class Dev(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client
        self.emoji = "<a:gdkid:868976838112841760>"

    @commands.command(
        aliases=["servers"], hidden=True, brief="Get the bot's server count"
    )
    @commands.is_owner()
    async def guilds(self, ctx: commands.Context):
        command = self.client.get_command("repl exec")
        await ctx.invoke(
            command, # type: ignore
            code='"".join(["\\n".join(["{0.name}: {1} members | {0.id}".format(g, len([m for m in g.members if not m.bot])) for g in client.guilds]), f"\\n\\n{len(client.guilds)} servers"])', # type: ignore
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
        e = discord.Embed(description="👋 Aight brb")
        await ctx.reply(embed=e)

        await self.client.close(restart=True)

    @commands.command(name="hi", brief='Say "Hi" to the bot', hidden=True)
    @commands.is_owner()
    async def hi(self, ctx: commands.Context):
        await ctx.reply("hi")


async def setup(client: NotGDKID):
    await client.add_cog(Dev(client=client))
