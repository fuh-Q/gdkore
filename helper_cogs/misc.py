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

from utils import CHOICES, BotEmojis

if TYPE_CHECKING:
    from discord import Message, Thread

    from helper_bot import NotGDKID
    from utils import NGKContext, OAuthCreds

    Interaction = discord.Interaction[NotGDKID]


class Misc(commands.Cog):
    DANK_MEMER_ID = 270904126974590976
    STUPIDLY_DECENT_ID = 890355226517860433
    TASK_MINUTES = 49
    THREADS_PURGE_CUTOFF = datetime(year=2023, month=7, day=3)
    THREAD_IDS = [
        1125273011201785987,  # gdkid
        1125273798397141034,  # toilet
        1125273927564918816,  # sam
        1125274051116535858,  # little shit
    ]

    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self._sleep_reminded = False
        self._reminder_task: asyncio.Task[None] | None = None
        self._purge_timers: Dict[int, asyncio.Task[None] | None] = {i: None for i in self.THREAD_IDS}

        self.invite_cmd = ContextMenu(name="invite bot", callback=self.invite_bot)
        self.client.tree.add_command(self.invite_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command("invite bot")

        if self._reminder_task is not None:
            self._reminder_task.cancel()

        for timer in self._purge_timers.values():
            if timer is not None:
                timer.cancel()

    async def _try_request(self, member: discord.Member, /, *, token: str) -> int:
        endpoint = f"{Route.BASE}/guilds/{member.guild.id}/members/{member.id}"
        headers = {"Authorization": f"Bot {self.client.http.token}", "Content-Type": "application/json"}
        json: Dict[str, Any] = {"access_token": token}

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
        endpoint = f"{Route.BASE}/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": self.client.user.id,
            "client_secret": self.client.oauth_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        assert self.client.session
        async with self.client.session.post(endpoint, data=data, headers=headers) as res:
            return await res.json()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != self.STUPIDLY_DECENT_ID:
            return

        member_creds = self.client.serverjail.get(str(member.id))
        if not member_creds:
            return

        status = await self._try_request(member, token=member_creds["access_token"])
        if status >= 400:  # probably needs a refresh
            new_creds = await self._do_refresh(refresh_token=member_creds["refresh_token"])
            self.client.serverjail[str(member.id)] = new_creds

        await self._try_request(member, token=member_creds["access_token"])

    @commands.Cog.listener("on_message")
    async def dank_msg_deleter(self, message: Message):
        class Delay(discord.ui.View):
            message: Message | None

            def __init__(self):
                self._postponed = False
                self.message = None

                super().__init__(timeout=8)

            async def on_timeout(self):
                assert self.message is not None
                self.postpone.disabled = True
                self.cancel.disabled = True

                if self._postponed:
                    return

                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass  # we tried

            async def interaction_check(self, interaction: Interaction):
                if interaction.user.id not in interaction.client.owner_ids:
                    await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="postpone 20s")
            async def postpone(self, interaction: Interaction, _):
                timer = cog._purge_timers[channel_id]
                if timer is not None:
                    timer.cancel()

                cog._purge_timers[channel_id] = interaction.client.loop.create_task(
                    task(wait=20), name=f"purge-{rn.hour}:{rn.minute}-{channel_id}"
                )

                self._postponed = True
                await interaction.response.edit_message(content="postponing...", view=None)

            @discord.ui.button(label="fuck off")
            async def cancel(self, *_):
                assert self.message is not None
                timer = cog._purge_timers[channel_id]
                if timer is not None:
                    timer.cancel()

                cog._purge_timers[channel_id] = None
                await self.message.delete()

        async def task(*, wait: int):
            assert isinstance(message.channel, Thread)
            await asyncio.sleep(wait - 10)

            view = Delay()
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

        cog = self  # for the delay view's scope -- DO NOT REMOVE

        rn = datetime.now(tz=ZoneInfo("America/Toronto"))
        self._purge_timers[channel_id] = self.client.loop.create_task(
            task(wait=90), name=f"purge-{rn.hour}:{rn.minute}-{channel_id}"
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

        if not message.guild:
            return

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
        await self.client.whitelist.put(guild_id, -1)

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
