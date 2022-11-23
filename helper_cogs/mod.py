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

#  fmt: off

muted: Callable[
    [discord.Member], str
] = (
    lambda user: f"""
{user.mention} has been muted forever.

L
"""
)

self_muted: Callable[
    [], str
] = (
    lambda: f"""
okay, you've muted yourself forever.

if you wanna get unmuted, dm `gdkid#0111` so he can laugh at you {BotEmojis.HAHALOL}

this message is also able to be seen by the entire server, because it really is just that funny
"""
)

insert_q: Callable[
    [int], str
] = lambda stop: """INSERT INTO stickyroles VALUES {0}
ON CONFLICT ON CONSTRAINT stickyroles_pkey
DO NOTHING""".format(
    ",".join(f"(${i}, ${i + 1})" for i in range(1, stop + 1, 2))
)

#  fmt: on


class Mod(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self.mute_user_cmd = ContextMenu(
            name="shut the fuck up", guild_ids=[self.client.AMAZE_GUILD_ID], callback=self.mute_user
        )

        self._ignore_ids: Set[int] = set()

        self.client.tree.add_command(self.mute_user_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command("shut the fuck up")

    def find_role(self, guild: discord.Guild, search: str) -> discord.Role:
        try:
            role = guild.get_role(int(search))
            if not role:
                raise ValueError
        except ValueError:
            role = match.extractOne(search, guild.roles)[0]  # type: ignore

        return role

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not after.guild.id == self.client.AMAZE_GUILD_ID:
            return

        if before.roles == after.roles:
            return

        if after.id in self._ignore_ids:
            self._ignore_ids.remove(after.id)
            return

        r = self.client.amaze_guild.get_role(self.client.AMAZE_GUILD_ID)
        added = tuple(set(after.roles) - set(before.roles) - {r})
        removed = tuple(set(before.roles) - set(after.roles) - {r})

        if added:
            args: Tuple[int, ...] = tuple(chain.from_iterable((after.id, r.id) for r in added))
            await self.client.db.execute(insert_q(len(added) * 2), *args)
        if removed:
            q = "DELETE FROM stickyroles WHERE"
            for i in range(1, len(removed) * 2 + 1, 2):
                base = "" if i == 1 else "OR"
                q += f"{base} user_id = ${i} AND role_id = ${i + 1} "
            args: Tuple[int, ...] = tuple(chain.from_iterable((after.id, r.id) for r in removed))
            await self.client.db.execute(q.strip(), *args)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.guild.id == self.client.AMAZE_GUILD_ID:
            return

        extra_roles: Set[discord.Role | None] = {member.guild.get_role(self.client.MEMBER_ROLE_ID)}

        q = """SELECT role_id FROM stickyroles
               WHERE user_id = $1"""
        roles: chain[discord.Role] = chain(
            map(lambda rec: member.guild.get_role(rec["role_id"]), await self.client.db.fetch(q, member.id)),  # type: ignore
            extra_roles,
        )

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
                reason=f"self-mute requested by {interaction.user.name}#{interaction.user.discriminator}",
            )
            await interaction.response.send_message(self_muted())
        elif interaction.guild.get_role(self.client.ADMIN_ROLE_ID) in interaction.user.roles:
            if isinstance(target, discord.Member):
                await target.add_roles(
                    discord.Object(self.client.MUTED_ROLE_ID),
                    reason=f"member mute requested by {interaction.user.name}#{interaction.user.discriminator}",
                )
                return await interaction.response.send_message(muted(target))
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
    async def bind_role(self, ctx: NGKContext, target: discord.User, *, role_search: str):
        guild = self.client.amaze_guild
        member = guild.get_member(target.id)

        role = self.find_role(guild, role_search)
        if not member:
            await self.client.db.execute(insert_q(2), target.id, role.id)
        else:
            await member.add_roles(role)

        await ctx.message.add_reaction(BotEmojis.YES)

    @commands.command(name="unbind", aliases=["unbindrole", "ub"])
    @commands.is_owner()
    async def unbind_role(self, ctx: NGKContext, target: discord.User, *, role_search: str | None = None):
        guild = self.client.amaze_guild
        member = guild.get_member(target.id)

        if not role_search:
            q = """DELETE FROM stickyroles
                   WHERE user_id = $1 RETURNING role_id"""
            rows = await self.client.db.fetch(q, target.id)
            if not rows:
                return await ctx.reply("nothing found")

            await ctx.reply(
                f"cleared {len(rows)} role(s) for <@!{target.id}>",
                allowed_mentions=discord.AllowedMentions(users=False),
                mention_author=True,
            )
            if member is None:
                return

            self._ignore_ids.add(member.id)
            roles = (role for r in rows if (role := guild.get_role(r["role_id"])) is not None)
            return await member.remove_roles(*roles, atomic=False)

        role = self.find_role(guild, role_search)
        if not member:
            q = """DELETE FROM stickyroles
                WHERE user_id = $1 AND role_id = $2"""
            await self.client.db.execute(q, target.id, role.id)
        else:
            await member.remove_roles(role)

        await ctx.message.add_reaction(BotEmojis.YES)


async def setup(client: NotGDKID):
    await client.add_cog(Mod(client=client))
