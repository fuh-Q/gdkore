from __future__ import annotations

import os
from typing import List, TYPE_CHECKING

import discord
from discord import Interaction
from discord.app_commands import command
from discord.ext import commands

from utils import BotEmojis

if TYPE_CHECKING:
    from helper_bot import NotGDKID
    from utils import NGKContext


class Misc(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @commands.command(name="whitelist", aliases=["wl"], hidden=True)
    @commands.is_owner()
    async def wl(self, ctx: NGKContext, guild_id: int):
        await self.client.whitelist.put(guild_id, None)

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="unwhitelist", aliases=["uwl"], hidden=True)
    @commands.is_owner()
    async def uwl(self, ctx: NGKContext, guild_id: int):
        try:
            await self.client.whitelist.remove(guild_id)
        except KeyError:
            return await ctx.try_react(emoji=BotEmojis.NO)

        if (guild := self.client.get_guild(guild_id)) is not None:
            await guild.leave()

        await ctx.try_react(emoji=BotEmojis.YES)

    @command(name="shoppingcart")
    async def _shoppingcart(self, interaction: Interaction):
        await interaction.response.send_message(
            "https://i.redd.it/3zhf6p3lrky41.jpg", ephemeral=True
        )


async def setup(client: NotGDKID):
    await client.add_cog(Misc(client=client))
