from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from helper_bot import NotGDKID


class Autorole(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id == self.client.AMAZE_GUILD_ID:
            await member.add_roles(
                member.guild.get_role(self.client.MEMBER_ROLE_ID),
                reason="amaze guild autorole"
            )

    
async def setup(client: NotGDKID):
    await client.add_cog(Autorole(client=client))
