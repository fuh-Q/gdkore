from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, TYPE_CHECKING
from zoneinfo import ZoneInfo

from discord.http import Route
from discord.app_commands import ContextMenu, command, guild_only
from discord.ext import commands

from utils import BotEmojis

if TYPE_CHECKING:
    from discord import Interaction, Member, Message

    from helper_bot import NotGDKID
    from utils import NGKContext, OAuthCreds


class Misc(commands.Cog):
    STUPIDLY_DECENT_ID = 890355226517860433
    ANDREW_ID = 603388080153559041

    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self.invite_cmd = ContextMenu(name="invite bot", callback=self.invite_bot)

        self._sleep_reminded = False
        self._reminder_task: asyncio.Task[None] | None = None

        self.client.tree.add_command(self.invite_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command("invite bot")

    async def _try_request(self, member: Member, /) -> int:
        endpoint = f"{Route.BASE}/guilds/{member.guild.id}/members/{member.id}"
        json: Dict[str, Any] = {"access_token": self.client.andrew_auth["access_token"]}
        headers = {"Authorization": f"Bot {self.client.http.token}", "Content-Type": "application/json"}

        if member.guild.me.guild_permissions.manage_roles:
            roles_to_add: List[str] = []
            for role in member.roles:
                if role.position < member.guild.me.top_role.position:
                    roles_to_add.append(str(role.id))

            json["roles"] = roles_to_add

        assert self.client.session
        async with self.client.session.put(endpoint, json=json, headers=headers) as res:
            return res.status

    async def _do_refresh(self, *, refresh_token: str) -> OAuthCreds:
        CLIENT_SECRET = "TICeRRfeHKL2JVATrcE-dgwwjLJVmyqQ"

        endpoint = f"{Route.BASE}/oauth2/token"
        data: Dict[str, Any] = {
            "client_id": self.client.user.id,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        assert self.client.session
        async with self.client.session.post(endpoint, data=data, headers=headers) as res:
            return await res.json()

    @commands.Cog.listener()
    async def on_member_remove(self, member: Member):
        if member.id != self.ANDREW_ID or member.guild.id != self.STUPIDLY_DECENT_ID:
            return

        status = await self._try_request(member)
        if status >= 400:  # probably needs a refresh
            new_creds = await self._do_refresh(refresh_token=self.client.andrew_auth["refresh_token"])
            self.client.andrew_auth = new_creds

        await self._try_request(member)

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        async def task():
            assert message.interaction
            await asyncio.sleep(3600)

            msg = f"{message.interaction.user.mention} oi giveaway time"
            hour = datetime.now(tz=ZoneInfo("America/Toronto")).hour
            if hour < 7:
                self._sleep_reminded = True
                msg += "\nalso go to sleep wtf"
            else:
                self._sleep_reminded = False

            await message.reply(msg)
            self._reminder_task = None

        assert message.guild
        if not message.interaction or message.guild.id != self.STUPIDLY_DECENT_ID:
            return

        if message.interaction.user.id not in self.client.owner_ids:
            return

        if message.interaction.name.startswith("giveaway"):
            rn = datetime.now(tz=ZoneInfo("America/Toronto"))
            if rn.hour < 7 and self._sleep_reminded:
                return

            if self._reminder_task is not None:
                self._reminder_task.cancel()

            self._reminder_task = self.client.loop.create_task(
                task(), name=f"Reminder-{rn.hour}:{rn.minute}-{int(rn.timestamp())}"
            )

    @guild_only()
    async def invite_bot(self, interaction: Interaction, member: Member):
        if not member.bot:
            return await interaction.response.send_message(f"{member.mention} is not a bot", ephemeral=True)

        url = f"https://discord.com/oauth2/authorize?client_id={member.id}&permissions=543312838143&scope=bot%20applications.commands"
        if member.id == self.client.user.id and interaction.user.id not in self.client.owner_ids:
            url = "https://discord.gg/ggZn8PaQed"

        return await interaction.response.send_message(
            f"[click here to invite {member.name}]({url}) (feel free to toggle the invite's permissions as needed)",
            ephemeral=True,
        )

    @commands.command(name="lastgaw", aliases=["lg"])
    @commands.is_owner()
    async def _lastgaw(self, ctx: NGKContext):
        t = self._reminder_task
        if not t:
            return await ctx.send("none found")

        await ctx.send(f"last giveaway done <t:{t.get_name().split('-')[-1]}:R>")

    @commands.command(name="whitelist", aliases=["wl"], hidden=True)
    @commands.is_owner()
    async def wl(self, ctx: NGKContext, guild_id: int):
        await self.client.whitelist.put(guild_id, None)

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="unwhitelist", aliases=["uwl"], hidden=True)
    @commands.is_owner()
    async def uwl(self, ctx: NGKContext, guild_id: int):
        try:
            await self.client.whitelist.remove(guild_id)
        except KeyError:
            return await ctx.try_react(emoji=BotEmojis.NO)

        if (guild := self.client.get_guild(guild_id)) is not None:
            await guild.leave()

        await ctx.try_react(emoji=BotEmojis.YES)

    @command(name="shoppingcart")
    async def _shoppingcart(self, interaction: Interaction):
        """the shopping cart theory"""
        await interaction.response.send_message("https://i.redd.it/3zhf6p3lrky41.jpg", ephemeral=True)


async def setup(client: NotGDKID):
    await client.add_cog(Misc(client=client))
