from __future__ import annotations

from typing import TYPE_CHECKING

from discord import Member
from discord.app_commands import ContextMenu, command, guild_only
from discord.ext import commands

from utils import BotEmojis

if TYPE_CHECKING:
    from discord import Interaction, Message

    from helper_bot import NotGDKID
    from utils import NGKContext


class Misc(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self.invite_cmd = ContextMenu(name="invite bot", callback=self.invite_bot)

        self.client.tree.add_command(self.invite_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command("invite bot")

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.channel.id == 749892811905564677 and message.author.id == 270904126974590976:
            await message.delete(delay=3)

    @guild_only()
    async def invite_bot(self, interaction: Interaction, member: Member):
        if not member.bot:
            return await interaction.response.send_message(f"{member.mention} is not a bot", ephemeral=True)

        url = f"https://discord.com/oauth2/authorize?client_id={member.id}&permissions=543312838143&scope=bot%20applications.commands"
        if member.id == self.client.user.id and interaction.user.id not in self.client.owner_ids:
            url = "https://discord.gg/ggZn8PaQed"

        return await interaction.response.send_message(
            f"[click here to invite {member.name}]({url}) (feel free to toggle the invite's permissions as needed)",
            ephemeral=True,
        )

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
        """the shopping cart theory"""
        await interaction.response.send_message("https://i.redd.it/3zhf6p3lrky41.jpg", ephemeral=True)


async def setup(client: NotGDKID):
    await client.add_cog(Misc(client=client))
