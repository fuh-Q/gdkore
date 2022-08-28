from __future__ import annotations

from typing import TYPE_CHECKING, List

from fuzzy_match import match

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
    
    def find_role(self, guild: discord.Guild, search: str) -> discord.Role:
        try:
            role: discord.Role | None = guild.get_role(int(search))
            if not role:
                raise ValueError
        except ValueError:
            role: discord.Role = match.extractOne(search, guild.roles)[0]
        
        return role
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not after.guild.id == self.client.AMAZE_GUILD_ID:
            return
        
        muted_role = after.guild.get_role(self.client.MUTED_ROLE_ID)
        
        if muted_role not in before.roles and muted_role in after.roles:
            q = """INSERT INTO stickyroles VALUES ($1, $2)
                    ON CONFLICT ON CONSTRAINT stickyroles_pkey
                    DO NOTHING
                """
        elif muted_role in before.roles and not muted_role in after.roles:
            q = """DELETE FROM stickyroles
                    WHERE user_id = $1 AND role_id = $2
                """
        else:
            return
        
        await self.client.db.execute(q, after.id, muted_role.id)
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        q = """SELECT role_id FROM stickyroles
                WHERE user_id = $1
            """
        roles: List[discord.Role] = list(map(
            lambda rec: member.guild.get_role(rec["role_id"]), await self.client.db.fetch(q, member.id)
        ))
        
        await member.add_roles(roles, reason="sticky roles")
    
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        q = """DELETE FROM stickyroles
                WHERE role_id = $1
            """
        await self.client.db.execute(q, role.id)
    
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
    
    @commands.command(name="bind", aliases=["bindrole", "br"])
    @commands.is_owner()
    async def bind_role(self, ctx: commands.Context, member: discord.Member, *, role_search: str):
        role = self.find_role(ctx.guild, role_search)
        q = """INSERT INTO stickyroles VALUES ($1, $2)
                ON CONFLICT ON CONSTRAINT stickyroles_pkey
                DO NOTHING
            """
        await self.client.db.execute(q, member.id, role.id)
        
        if role not in member.roles:
            await member.add_roles(role)
        
        await ctx.message.add_reaction(BotEmojis.YES)
    
    @commands.command(name="unbind", aliases=["unbindrole", "ub"])
    @commands.is_owner()
    async def unbind_role(self, ctx: commands.Context, member: discord.Member, *, role_search: str | None = None):
        if not role_search:
            q = """DELETE FROM stickyroles
                    WHERE user_id = $1
                """
            await self.client.db.execute(q, member.id)
            return await ctx.reply(
                f"all sticky roles cleared for `{member.name}`", mention_author=True
            )
        
        role = self.find_role(ctx.guild, role_search)
        q = """DELETE FROM stickyroles
                WHERE user_id = $1 AND role_id = $2
            """
        await self.client.db.execute(q, member.id, role.id)
        
        await ctx.message.add_reaction(BotEmojis.YES)

    
async def setup(client: NotGDKID):
    await client.add_cog(Mod(client=client))
