from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

from PIL import Image

import discord
from discord import Interaction
from discord.app_commands import ContextMenu, command, guild_only
from discord.ext import commands

if TYPE_CHECKING:
    from helper_bot import NotGDKID


class Misc(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        
        self.client.tree.add_command(ContextMenu(
            name="flip them off",
            callback=self.middle_finger
        ))
    
    @guild_only()
    async def middle_finger(self, interaction: Interaction, user: discord.User):
        def runner(avatar: bytes) -> discord.File:
            with io.BytesIO(avatar) as buffer:
                with Image.open(buffer) as pfp:
                    with Image.open("assets/finger.png") as finger:
                        pfp.paste(finger, (100, 100), finger)
                        pfp.save(buffer, "png")
            
                return discord.File(buffer.getvalue(), "fu.png")
        
        content = f"{user.mention} {interaction.user.display_name} tells me to tell you to fuck off"
        avatar = interaction.user.avatar.with_size(256)
        
        await interaction.response.send_message(
            content=content,
            file=await asyncio.to_thread(runner, await avatar.read())
        )
    
    @command(name="shoppingcart")
    async def _shoppingcart(interaction: Interaction):
        await interaction.response.send_message(
            "https://i.redd.it/3zhf6p3lrky41.jpg", ephemeral=True
        )

    
async def setup(client: NotGDKID):
    await client.add_cog(Misc(client=client))
