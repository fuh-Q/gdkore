from __future__ import annotations

from typing import TYPE_CHECKING, List

import discord
from discord import Interaction
from discord.ext import commands
from discord.app_commands import command

from cogs.mazes import InventoryEntry
from utils import BotEmojis

if TYPE_CHECKING:
    from bot import Amaze


class Inventory(commands.Cog):
    def __init__(self, client: Amaze) -> None:
        self.client = client
    
    @command(name="inventory")
    async def view_inventory(self, interaction: Interaction):
        """view your inventory"""
        
        id_name_emoji = {
            "max_dash": ("max dashes", BotEmojis.MAZE_DASH_ENABLED)
        }
        
        q = """SELECT * FROM inventory
                WHERE user_id = $1
            """
        inventory: List[InventoryEntry] = await self.client.db.fetch(q, interaction.user.id)
        item_str = ""
        for item in inventory:
            name, emoji = id_name_emoji[item["item_id"]]
            item_str += f"{emoji} — **{name}** [`{item['item_count']}`]\n\u200b"
        
        e = discord.Embed(
            description=item_str,
            colour=None,
        ).set_author(
            name=f"{interaction.user.name}'s inventory", icon_url=interaction.user.avatar.url
        ).set_footer(
            text="you can get more dashes by voting! /vote"
        )
        
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(client: Amaze):
    await client.add_cog(Inventory(client=client))
