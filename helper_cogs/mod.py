from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import Interaction
from discord.app_commands import ContextMenu, guild_only
from discord.ext import commands

from utils import BotEmojis

if TYPE_CHECKING:
    from helper_bot import NotGDKID


muted = lambda user: f"""
hello, i have been summoned by the great `{user.name}` to restore some peace and sanity in this hell of a server.

their desires are simple - i literally said it one line above

and as for fulfilling this desire, i shall utilise the neverfailing power of the **indefinite mute**.

L
"""

self_muted = lambda: f"""
okay, you've muted yourself forever.

if you wanna get unmuted, dm `gdkid#0111` so he can laugh at you {BotEmojis.HAHALOL}

this message is also able to be seen by the entire server, because it really is just that funny
"""


class Mod(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self.mute_user = ContextMenu(
            name="shut the fuck up",
            guild_ids=[self.client.AMAZE_GUILD_ID],
            callback=self.mute_user
        )
        
        self.client.tree.add_command(self.mute_user)
    
    @guild_only()
    async def mute_user(self, interaction: Interaction, member: discord.Member):
        if interaction.guild.get_role(self.client.ADMIN_ROLE_ID) in interaction.user.roles:
            await member.add_roles(
                discord.Object(self.client.MUTED_ROLE_ID),
                reason=f"member mute requested by {interaction.user.name}#{interaction.user.discriminator}"
            )
            await interaction.response.send_message(
                muted(interaction.user)
            )
        elif interaction.user.id == member.id:
            await member.add_roles(
                discord.Object(self.client.MUTED_ROLE_ID),
                reason=f"self-mute requested by {interaction.user.name}#{interaction.user.discriminator}"
            )
            await interaction.response.send_message(
                self_muted()
            )
        else:
            await interaction.response.send_message(
                f"L no perms {BotEmojis.HAHALOL}",
                ephemeral=True,
            )

    
async def setup(client: NotGDKID):
    await client.add_cog(Mod(client=client))
