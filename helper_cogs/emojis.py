from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from helper_bot import NotGDKID


class Emojis(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    
async def setup(client: NotGDKID):
    await client.add_cog(Emojis(client=client))
