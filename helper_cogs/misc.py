from __future__ import annotations

import json
from typing import TYPE_CHECKING

import discord
from discord import Interaction
from discord.app_commands import command
from discord.ext import commands

from utils import BotEmojis

if TYPE_CHECKING:
    from helper_bot import NotGDKID


class Misc(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    async def update_whitelisted_file(self, ctx: commands.Context):
        data = {self.client.get_guild(id).name: id for id in self.client.whitelisted_guilds}
        with open("config/whitelisted.json", "w") as f:
            json.dump(data, f, indent=2)

        try:
            await ctx.message.add_reaction(BotEmojis.YES)
        except discord.Forbidden:
            pass

    @commands.command(name="whitelist", aliases=["wl"], hidden=True)
    @commands.is_owner()
    async def wl(self, ctx: commands.Context, guild_id: int):
        self.client.whitelisted_guilds.add(guild_id)

        try:
            await ctx.message.add_reaction(BotEmojis.YES)
        except discord.Forbidden:
            pass

    @commands.command(name="unwhitelist", aliases=["uwl"], hidden=True)
    @commands.is_owner()
    async def uwl(self, ctx: commands.Context, guild_id: int):
        self.client.whitelisted_guilds.remove(guild_id)
        await self.update_whitelisted_file(ctx)

        if (guild := self.client.get_guild(guild_id)):
            await guild.leave()

    @command(name="shoppingcart")
    async def _shoppingcart(self, interaction: Interaction):
        await interaction.response.send_message(
            "https://i.redd.it/3zhf6p3lrky41.jpg", ephemeral=True
        )


async def setup(client: NotGDKID):
    await client.add_cog(Misc(client=client))
