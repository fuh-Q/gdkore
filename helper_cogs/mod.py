from __future__ import annotations

from itertools import chain
from typing import Callable, Tuple, Set, TYPE_CHECKING

from fuzzy_match import match

import discord
from discord import Interaction
from discord.app_commands import ContextMenu, guild_only
from discord.ext import commands

from utils import BotEmojis

if TYPE_CHECKING:
    from helper_bot import NotGDKID
    from utils import NGKContext

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

insert_q: Callable[[int], str] = lambda stop: \
    """INSERT INTO stickyroles VALUES {0}
    ON CONFLICT ON CONSTRAINT stickyroles_pkey
    DO NOTHING""".format(",".join(
        f"(${i}, ${i + 1})" for i in range(1, stop + 1, 2)
    ))

class Mod(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self.mute_user_cmd = ContextMenu(
            name="shut the fuck up",
            guild_ids=[self.client.AMAZE_GUILD_ID],
            callback=self.mute_user
        )

        self.client.tree.add_command(self.mute_user_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command("shut the fuck up")

    async def cog_check(self, ctx: NGKContext):
        return ctx.guild and ctx.guild.id == self.client.AMAZE_GUILD_ID

    def find_role(self, guild: discord.Guild, search: str) -> discord.Role:
        try:
            role = guild.get_role(int(search))
            if not role:
                raise ValueError
        except ValueError:
            role = match.extractOne(search, guild.roles)[0] # type: ignore

        return role

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not after.guild.id == self.client.AMAZE_GUILD_ID:
            return

        if before.roles == after.roles:
            return

        added = tuple(r for r in after.roles
                      if r not in before.roles
                      and r.id != self.client.MEMBER_ROLE_ID)

        removed = tuple(r for r in before.roles
                        if r not in after.roles
                        and r.id != self.client.MEMBER_ROLE_ID)

        if added:
            args: Tuple[int, ...] = tuple(chain.from_iterable((after.id, r.id) for r in added))
            await self.client.db.execute(insert_q(len(added)), *args)
        if removed:
            q = "DELETE FROM stickyroles WHERE"
            for i in range(1, len(removed) + 1, 2):
                base = "" if i == 1 else "OR"
                q += f"{base} user_id = ${i} AND role_id = ${i + 1} "
            args: Tuple[int, ...] = tuple(chain.from_iterable((after.id, r.id) for r in removed))
            await self.client.db.execute(q.strip(), *args)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.guild.id == self.client.AMAZE_GUILD_ID:
            return

        extra_roles: Set[discord.Role | None] = {
            member.guild.get_role(self.client.MEMBER_ROLE_ID)
        }

        q = """SELECT role_id FROM stickyroles
               WHERE user_id = $1"""
        roles: chain[discord.Role] = chain(map( # type: ignore
            lambda rec: member.guild.get_role(rec["role_id"]), await self.client.db.fetch(q, member.id)
        ), extra_roles)

        await member.add_roles(*roles, reason="sticky roles", atomic=False)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        if not role.guild.id == self.client.AMAZE_GUILD_ID:
            return

        q = """DELETE FROM stickyroles
               WHERE role_id = $1"""
        await self.client.db.execute(q, role.id)

    @guild_only()
    async def mute_user(self, interaction: Interaction, target: discord.Member):
        assert interaction.guild and isinstance(interaction.user, discord.Member)
        if interaction.user.id == target.id:
            await target.add_roles(
                discord.Object(self.client.MUTED_ROLE_ID),
                reason=f"self-mute requested by {interaction.user.name}#{interaction.user.discriminator}"
            )
            await interaction.response.send_message(self_muted())
        elif interaction.guild.get_role(self.client.ADMIN_ROLE_ID) in interaction.user.roles:
            if isinstance(target, discord.Member):
                await target.add_roles(
                    discord.Object(self.client.MUTED_ROLE_ID),
                    reason=f"member mute requested by {interaction.user.name}#{interaction.user.discriminator}"
                )
                await interaction.response.defer(ephemeral=True)
                return await interaction.delete_original_response()
                #return await interaction.response.send_message(muted(interaction.user))
            await self.client.db.execute(insert_q(2), target.id, self.client.MUTED_ROLE_ID)
            await interaction.response.send_message(
                "this user is not in the server, but they've been binded with the sticky role"
            )
        else:
            await interaction.response.send_message(
                f"L no perms {BotEmojis.HAHALOL}",
                ephemeral=True,
            )

    @commands.command(name="bind", aliases=["bindrole", "br"])
    @commands.is_owner()
    @commands.guild_only()
    async def bind_role(self, ctx: NGKContext, target: discord.User | discord.Member, *, role_search: str):
        assert ctx.guild is not None
        role = self.find_role(ctx.guild, role_search)
        if isinstance(target, discord.User):
            await self.client.db.execute(insert_q(2), target.id, role.id)

        elif isinstance(target, discord.Member) and role not in target.roles:
            await target.add_roles(role)

        await ctx.message.add_reaction(BotEmojis.YES)

    @commands.command(name="unbind", aliases=["unbindrole", "ub"])
    @commands.is_owner()
    @commands.guild_only()
    async def unbind_role(self, ctx: NGKContext, target: discord.User, *, role_search: str | None = None):
        assert ctx.guild is not None
        if not role_search:
            q = """DELETE FROM stickyroles
                   WHERE user_id = $1"""
            await self.client.db.execute(q, target.id)
            return await ctx.reply(
                f"all sticky roles cleared for `{target.name}`", mention_author=True
            )

        role = self.find_role(ctx.guild, role_search)
        q = """DELETE FROM stickyroles
               WHERE user_id = $1 AND role_id = $2"""
        await self.client.db.execute(q, target.id, role.id)

        await ctx.message.add_reaction(BotEmojis.YES)


async def setup(client: NotGDKID):
    await client.add_cog(Mod(client=client))
