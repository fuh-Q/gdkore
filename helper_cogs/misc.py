from __future__ import annotations

import asyncio
import logging
import time
import random
import re
from collections.abc import Collection
from datetime import datetime
from fractions import Fraction
from typing import Any, Dict, List, Literal, Tuple, TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord import ui, ButtonStyle, SelectOption
from discord.http import Route
from discord.app_commands import ContextMenu, command
from discord.ext import commands

from utils import CHOICES, BotEmojis, View

if TYPE_CHECKING:
    from discord import Message, Thread
    from discord.message import MessageComponentType

    from helper_bot import NotGDKID
    from utils import NGKContext, OAuthCreds

    Interaction = discord.Interaction[NotGDKID]
    OfferTargets = Collection[Literal["buying", "selling", "item"] | str]

log = logging.getLogger(__name__)

OFFER_ITEM_PAT = re.compile(r"^\*\*(?P<verb>Buying|Selling)\s(?P<amount>[\d,]+)\s<a?:\w+:\d{17,}>\s(?P<name>.+)\*\*$", re.A)
FOR_ITEM_PAT = re.compile(r"^<a?:\w+:\d{17,}>\sFor:\s(?P<amount>[\d,]+)x\s<a?:\w+:\d{17,}>\s(?P<name>.+)$", re.A)

EVENT_MUTE = {
    # guild id -> muted role id
    1309946222018170951: 1309949786308214824,
    1309689611701714965: 1309928701483417741,
    1309689566336389292: 1309928702838177955,
    1309689524846198908: 1309928703962382403,
    1309689473394802830: 1309928705497497691,
    1309689437164404777: 1309928706478837881,
    1309689647370338324: 1309928712971616256,
    1309689323699830896: 1309928714540285993,
    1309689217407778826: 1309928715421089804,
    1309689175016079460: 1309928716431917150,
    1309689123094921236: 1309928717790875653,
    1299189004146839592: 1309928718692782080,
    1309980051457970267: 1309981040764260403,
    1309979984768798842: 1309981051698811002,
    1309979948122902538: 1309981067662589952,
    1309979912299352174: 1309981068484673658,
    1309979874277982218: 1309981079964352633,
    1309979836357546004: 1309981088281788559,
    1309979796318584832: 1309981096124878901,
    1309979738638520460: 1309981104911945768,
}


def _human_friendly_value(inp: str, /) -> str:
    split = inp.split(",")
    unit = ("", "k", "mil", "b", "t")[len(split) - 1]
    if len(split) == 1:
        return split[0]

    front, decimal = split[0], split[1][0]
    if decimal == "0":
        return f"{front}{unit}"

    return f"{front}.{decimal}{unit}"


def _gen_ad_impl(
    offers: Collection[str],
    *,
    components: List[MessageComponentType],
    targets: OfferTargets,
) -> str:
    def is_my_offer() -> bool:
        this_row = components[int(idx > 1) + 2]  # offset 2 component rows down
        assert isinstance(this_row, discord.ActionRow)

        this_component = this_row.children[idx % 2]
        assert isinstance(this_component, ui.Button)

        return this_component.style != ButtonStyle.green

    ret: List[str] = []
    offer_lines: Dict[Tuple[str, str], int] = {}
    for idx, offer in enumerate(offers):
        if not is_my_offer():
            continue

        lines = offer.splitlines()
        first, fallback, value = lines[:3]

        offer_id = offer[-7:].strip()
        item = OFFER_ITEM_PAT.search(first)
        assert item is not None

        partial = "Partial Accepting Allowed" in offer
        coin_offer = "Value per Unit" in value
        lowered_verb = item["verb"].lower()

        if coin_offer and lowered_verb in targets:
            ret.append("")
            amount = _human_friendly_value(value.split()[-1])
            key = (item["name"], amount)
            line = offer_lines.get(key)
            if line:
                ret[line] += f", **{offer_id}**"
                continue

            offer_lines[key] = idx
            ret[-1] += f"{lowered_verb} {item['name'].lower()} "
            ret[-1] += f"⏣ {amount}" if value[-4] != "," else amount
            ret[-1] += " each " if partial else " "
            ret[-1] += f"--> **{offer_id}**"
        elif not coin_offer and "item" in targets:
            ret.append("")
            for_item = FOR_ITEM_PAT.search(fallback)
            assert for_item is not None

            item_qty = int(item["amount"].replace(",", ""))
            for_qty = int(for_item["amount"].replace(",", ""))
            a, b = Fraction(item_qty, for_qty).as_integer_ratio()
            key = (item["name"], f"{a}:{b}")
            line = offer_lines.get(key)
            if line:
                ret[line] += f", **{offer_id}**"
                continue

            ret[-1] += f"my {item['name'].lower()} for your {for_item['name'].lower()} {a}:{b} --> **{offer_id}**"

    if not ret:
        return "none of these offers are yours"

    return "\n".join(ret)


class Filter(View, auto_defer=True):
    interaction: Interaction
    opts = [
        SelectOption(label="buy offers", value="buying", default=True),
        SelectOption(label="sell offers", value="selling", default=True),
        SelectOption(label="item-for-item offers", value="item", default=True),
    ]

    def __init__(self, owner_id: int, *, offers: OfferTargets, components: List[MessageComponentType]):
        super().__init__(timeout=self.TIMEOUT)
        self._owner_id = owner_id
        self._offers = offers
        self._components = components
        self._codeblocked = False

        self.select = ui.Select(options=self.opts, min_values=1, max_values=len(self.opts), row=0)
        self.select._values = [o.value for o in self.opts]
        self.add_item(self.select)

    async def interaction_check(self, interaction: Interaction, _) -> bool:
        if interaction.user.id != self._owner_id:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.disable_all(exclude_urls=True)

        try:
            await self.interaction.edit_original_response(view=self)
        except discord.HTTPException:
            pass  # we tried

    @ui.button(label="go", style=ButtonStyle.primary, row=1)
    async def generate(self, interaction: Interaction, button: ui.Button):
        self.stop()
        ad = _gen_ad_impl(self._offers, components=self._components, targets=self.select.values)
        ad = f"```{ad}```" if self._codeblocked else ad
        await interaction.response.edit_message(
            content=ad or "no ads of the selected types found",
            embed=None,
            view=None,
        )

    @ui.button(label="codeblocked?", emoji=BotEmojis.NO, row=1)
    async def codeblocked(self, interaction: Interaction, button: ui.Button):
        self._codeblocked = not self._codeblocked
        button.emoji = BotEmojis.YES if self._codeblocked else BotEmojis.NO
        await interaction.response.edit_message(view=self)


class Misc(commands.Cog):
    DANK_MEMER_ID = 270904126974590976
    STUPIDLY_DECENT_ID = 890355226517860433
    TASK_MINUTES = 52
    THREADS_PURGE_CUTOFF = datetime(year=2023, month=7, day=3)
    THREAD_IDS = [
        1125273011201785987,  # gdkid
        1125273798397141034,  # toilet
        1125273927564918816,  # sam
        1169390818524667944,  # little shit
    ]

    EVENT_BLACKLIST = {
        # event name, event timeout
        "trivia night": 300,
        "anti-rizz": 300,
        "item guesser": 300,
        "reverse reverse": 300,
        "dice champs": 600,
        "boss battle": 600,
    }

    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self._sleep_reminded = False
        self._reminder_task: asyncio.Task[None] | None = None
        self._purge_timers: Dict[int, asyncio.Task[None] | None] = {i: None for i in self.THREAD_IDS}

        self.invite_cmd = ContextMenu(name="invite bot", callback=self.invite_bot)
        self.client.tree.add_command(self.invite_cmd)

        self.generate_ad_cmd = ContextMenu(name="generate ad", callback=self.generate_ad)
        self.client.tree.add_command(self.generate_ad_cmd)

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

    async def _try_refresh(self, *, refresh_token: str) -> OAuthCreds | None:
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
            if res.status != 200:
                return

            return await res.json()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != self.STUPIDLY_DECENT_ID:
            return

        member_creds = self.client.serverjail.get(str(member.id))
        if not member_creds:
            return

        status = await self._try_request(member, token=member_creds["access_token"])
        if 200 <= status < 300:
            return

        # probably needs a refresh
        new_creds = await self._try_refresh(refresh_token=member_creds["refresh_token"])
        if new_creds:
            self.client.serverjail[str(member.id)] = new_creds
            await self._try_request(member, token=member_creds["access_token"])
        else:
            del self.client.serverjail[str(member.id)]

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

        if message.author.id == self.client.user.id:
            return

        channel_id = message.channel.id
        if channel_id not in self.THREAD_IDS:
            return

        timer = self._purge_timers[channel_id]
        if timer is not None:
            timer.cancel()

        cog = self  # for the delay view's scope -- DO NOT REMOVE

        rn = datetime.now(tz=ZoneInfo("America/Toronto"))
        self._purge_timers[channel_id] = self.client.loop.create_task(
            task(wait=90), name=f"purge-{rn.hour}:{rn.minute}-{channel_id}"
        )

    @commands.Cog.listener("on_message")
    async def giveaway_reminder(self, message: Message):
        async def task():
            assert message.interaction
            await asyncio.sleep(60 * self.TASK_MINUTES)

            msg = f"{message.interaction.user.mention} oi giveaway time"
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

        if message.interaction.name.startswith("giveaway create"):
            rn = datetime.now(tz=ZoneInfo("America/Toronto"))
            if rn.hour < 7 and self._sleep_reminded:
                return

            if self._reminder_task is not None:
                self._reminder_task.cancel()

            self._reminder_task = self.client.loop.create_task(
                task(), name=f"Reminder-{rn.hour}:{rn.minute}-{int(rn.timestamp())}"
            )

    @commands.Cog.listener("on_message")
    async def event_suppression(self, message: Message):
        if not message.guild or message.author.id != self.DANK_MEMER_ID:
            return
        assert isinstance(message.author, discord.Member)

        if not message.guild.name.startswith("event server"):
            return

        if not not message.guild.id in EVENT_MUTE:
            return

        title = message.embeds[0].title
        if not title or title.lower() not in self.EVENT_BLACKLIST:
            return

        role = message.guild.get_role(EVENT_MUTE[message.guild.id])
        if not role:
            return await message.reply(f"suppression role not found for this guild")

        await message.author.add_roles(role)
        await message.add_reaction("\N{SPEAKER WITH CANCELLATION STROKE}")

        timeout = self.EVENT_BLACKLIST[title.lower()]
        await asyncio.sleep(timeout + 30)
        await message.author.remove_roles(role)

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

    async def generate_ad(self, interaction: Interaction, message: discord.Message):
        fail = interaction.response.send_message("no \N{SKULL}", ephemeral=True)
        if message.author.id != self.DANK_MEMER_ID or not message.embeds:
            return await fail

        e = message.embeds[0]
        if e.title != "Market" or not e.description or not message.components:
            return await fail

        offers = e.description.split("\n\n")[1:]  # first item is just instructions, not an offer

        if not offers:
            return await interaction.response.send_message("there are no offers", ephemeral=True)

        view = Filter(interaction.user.id, offers=offers, components=message.components)

        view.interaction = interaction
        await interaction.response.send_message(
            embed=discord.Embed(description="choose offer types to include in your ad"),
            view=view,
            ephemeral=True,
        )

    @commands.group(name="event")
    @commands.is_owner()
    @commands.guild_only()
    async def events(self, _):
        pass

    @events.command(name="setup")
    async def eventsetup(self, ctx: NGKContext):
        assert ctx.guild and isinstance(ctx.me, discord.Member)
        if ctx.guild.id in EVENT_MUTE:
            return await ctx.reply("already done")

        if not ctx.me.guild_permissions > discord.Permissions(8):
            return await ctx.reply("bro what u on, no perms la")

        dank = ctx.guild.get_member(270904126974590976)
        if not dank:
            return await ctx.reply("add dank first")

        dank_role = discord.utils.find(lambda r: r.is_bot_managed(), dank.roles)
        assert dank_role and ctx.guild.self_role
        if dank_role.position > ctx.guild.self_role.position:
            return await ctx.reply("change the order of our roles")

        await dank_role.edit(permissions=discord.Permissions.none())

        role = await ctx.guild.create_role(name="fuck off", hoist=True)
        await ctx.guild.edit_role_positions({dank: 1, role: 2})
        await ctx.guild.text_channels[0].edit(overwrites={role: discord.PermissionOverwrite(send_messages=False)})
        await ctx.reply(f"add this to the mute role dict in `misc.py`: `{ctx.guild.id}: {role.id}`")

        if ctx.guild.id not in EVENT_MUTE:
            EVENT_MUTE[ctx.guild.id] = role.id

    @commands.command(name="lastgaw", aliases=["lw", "lg"])
    @commands.is_owner()
    async def _lastgaw(self, ctx: NGKContext):
        task = self._reminder_task
        if not task:
            return await ctx.send("none found")

        await ctx.send(f"last giveaway started <t:{task.get_name().split('-')[-1]}:R>")

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
