from __future__ import annotations

import asyncio
from io import BytesIO
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
    
    async def cog_unload(self) -> None:
        self.client.tree.remove_command("flip them off")
    
    @guild_only()
    async def middle_finger(self, interaction: Interaction, user: discord.User):
        def runner(avatar: bytes) -> discord.File:
            with BytesIO(avatar) as buffer:
                with Image.open(buffer) as pfp:
                    with Image.open("assets/finger.png").convert("RGBA") as finger:
                        pfp.paste(finger, (138, pfp.height - finger.height), finger)
                        buffer.seek(0)
                        pfp.save(buffer, "png")
                        buffer.seek(0)
            
                return discord.File(buffer, "fu.png")
        
        await interaction.response.defer()
        content = f"{user.mention} {interaction.user.display_name} told me to flip you off"
        avatar = interaction.user.avatar.with_size(256)
        
        await interaction.followup.send(
            content=content,
            file=await asyncio.to_thread(runner, await avatar.read())
        )
    
    @command(name="shoppingcart")
    async def _shoppingcart(self, interaction: Interaction):
        await interaction.response.send_message(
            "https://i.redd.it/3zhf6p3lrky41.jpg", ephemeral=True
        )

    
async def setup(client: NotGDKID):
    await client.add_cog(Misc(client=client))
