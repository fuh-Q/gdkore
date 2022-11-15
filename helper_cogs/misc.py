from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

from discord import Interaction
from discord.app_commands import command
from discord.ext import commands

if TYPE_CHECKING:
    from helper_bot import NotGDKID


class Misc(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @command(name="shoppingcart")
    async def _shoppingcart(self, interaction: Interaction):
        await interaction.response.send_message(
            "https://i.redd.it/3zhf6p3lrky41.jpg", ephemeral=True
        )


async def setup(client: NotGDKID):
    await client.add_cog(Misc(client=client))
