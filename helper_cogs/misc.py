from __future__ import annotations

import asyncio
import time
import random
from datetime import datetime
from typing import Any, Dict, List, TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord.http import Route
from discord.app_commands import ContextMenu, command
from discord.ext import commands
from discord.interactions import Interaction

from utils import CHOICES, BotEmojis

if TYPE_CHECKING:
    from discord import Interaction, Message, Thread

    from helper_bot import NotGDKID
    from utils import NGKContext, OAuthCreds


class Misc(commands.Cog):
    DANK_MEMER_ID = 270904126974590976
    STUPIDLY_DECENT_ID = 890355226517860433
    ANDREW_ID = 603388080153559041
    TASK_MINUTES = 49
    THREADS_PURGE_CUTOFF = datetime(year=2023, month=5, day=27)
    THREAD_IDS = [
        1111853523794149386,  # gdkid
        1111853402801045545,  # toilet
        1111853274983829616,  # sam
    ]

    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self.invite_cmd = ContextMenu(name="invite bot", callback=self.invite_bot)

        self._sleep_reminded = False
        self._reminder_task: asyncio.Task[None] | None = None

        self._purge_timers: Dict[int, asyncio.Task[None] | None] = {i: None for i in self.THREAD_IDS}

        self.client.tree.add_command(self.invite_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command("invite bot")

    async def _try_request(self, member: discord.Member, /) -> int:
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
    async def on_member_remove(self, member: discord.Member):
        if member.id != self.ANDREW_ID or member.guild.id != self.STUPIDLY_DECENT_ID:
            return

        status = await self._try_request(member)
        if status >= 400:  # probably needs a refresh
            new_creds = await self._do_refresh(refresh_token=self.client.andrew_auth["refresh_token"])
            self.client.andrew_auth = new_creds

        await self._try_request(member)

    @commands.Cog.listener("on_message")
    async def dank_msg_deleter(self, message: Message):
        class Delay(discord.ui.View):
            message: Message | None

            def __init__(self, *, cog: Misc):
                self.cog = cog
                self._postponed = False

                self.message = None

                super().__init__(timeout=8)

            async def on_timeout(self):
                assert self.message
                self.postpone.disabled = True

                if self._postponed:
                    return

                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass  # we tried

            async def interaction_check(self, interaction: Interaction):
                if interaction.user.id not in self.cog.client.owner_ids:
                    await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="postpone 20s")
            async def postpone(self, interaction: Interaction, _):
                timer = self.cog._purge_timers[channel_id]
                if timer is not None:
                    timer.cancel()

                self.cog._purge_timers[channel_id] = self.cog.client.loop.create_task(
                    task(wait=20), name=f"purge-{rn.hour}:{rn.minute}-{channel_id}"
                )

                self._postponed = True
                await interaction.response.edit_message(content="postponing...", view=None)

        async def task(*, wait: int):
            assert isinstance(message.channel, Thread)
            await asyncio.sleep(wait - 10)

            view = Delay(cog=self)
            msg = await message.channel.send(f"purging <t:{int(time.time()+10)}:R>", view=view)
            view.message = msg

            await asyncio.sleep(10)
            await message.channel.purge(limit=None, after=self.THREADS_PURGE_CUTOFF)
            self._purge_timers[channel_id] = None

        if message.channel.id not in self.THREAD_IDS:
            return

        channel_id = message.channel.id
        if self._purge_timers[channel_id] is not None:
            return

        rn = datetime.now(tz=ZoneInfo("America/Toronto"))
        self._purge_timers[channel_id] = self.client.loop.create_task(
            task(wait=60), name=f"purge-{rn.hour}:{rn.minute}-{channel_id}"
        )

    @commands.Cog.listener("on_message")
    async def work_reminder(self, message: Message):
        async def task():
            assert message.interaction
            await asyncio.sleep(60 * self.TASK_MINUTES)

            msg = f"{message.interaction.user.mention} oi time to </work shift:1011560371267579942>"
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

        if message.interaction.name == "work shift":
            rn = datetime.now(tz=ZoneInfo("America/Toronto"))
            if rn.hour < 7 and self._sleep_reminded:
                return

            if self._reminder_task is not None:
                self._reminder_task.cancel()

            self._reminder_task = self.client.loop.create_task(
                task(), name=f"Reminder-{rn.hour}:{rn.minute}-{int(rn.timestamp())}"
            )

    async def invite_bot(self, interaction: Interaction, user: discord.User):
        if not user.bot:
            return await interaction.response.send_message(f"{user.mention} is not a bot", ephemeral=True)

        url = f"https://discord.com/oauth2/authorize?client_id={user.id}&permissions=543312838143&scope=bot%20applications.commands"
        if user.id == self.client.user.id and interaction.user.id not in self.client.owner_ids:
            url = "https://discord.gg/ggZn8PaQed"

        return await interaction.response.send_message(
            f"[click here to invite {user.name}]({url}) (feel free to toggle the invite's permissions as needed)",
            ephemeral=True,
        )

    @commands.command(name="lastwork", aliases=["lw", "lg"])
    @commands.is_owner()
    async def _lastgaw(self, ctx: NGKContext):
        t = self._reminder_task
        if not t:
            return await ctx.send("none found")

        await ctx.send(f"you last worked <t:{t.get_name().split('-')[-1]}:R>")

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
