import datetime
import json
import random
import re
import sys
from typing import Any, Dict, Generator, Optional, SupportsInt, Type

import discord
from discord import Interaction, InteractionMessage, PartialEmoji, User
from discord.ext import commands
from discord.gateway import DiscordWebSocket
from discord.ui import Button, Item, View, button

CHOICES = [
    "no",
    "its not your menu",
    "don't think you can use this menu mate",
    "you cant use that menu... but you *can* watch rick roll\n\nhttps://tenor.com/view/dance-moves-dancing-singer-groovy-gif-17029825",
    "couldn't verify that you can use this menu!",
    "roses are red\nviolets are blue\nay hol up you can't use this menu",
    "can i see your non-existent proof that you have control over this paginator?",
]


def get_member_count(client: commands.Bot) -> int:
    """
    Gets the total count of members the bot can see. Useful when you don't have `Intents.members` enabled

    Arguments
    ---------
    client: `Bot`
        The bot to get the member count of

    Returns
    -------
    get_member_count: `int`
        The total amount of members
    """
    return sum([guild.member_count for guild in client.guilds])


def all_casings(input_string: str) -> Generator[str, None, None]:
    """
    A generator that yields every combination of lowercase and uppercase in a given string

    Arguments
    ---------
    input_string: `str`
        The string to iterate through

    Returns
    -------
    all_casings: Generator[`str`]
        A generator object yielding every combination of lowercase and uppercase
    """
    if not input_string:
        yield ""
    else:
        first = input_string[:1]
        if first.lower() == first.upper():
            for sub_casing in all_casings(input_string[1:]):
                yield first + sub_casing
        else:
            for sub_casing in all_casings(input_string[1:]):
                yield first.lower() + sub_casing
                yield first.upper() + sub_casing


def humanize_timedelta(
    *,
    timedelta: Optional[datetime.timedelta] = None,
    seconds: Optional[SupportsInt] = None,
) -> str:
    """
    Convert a `timedelta` object or time in seconds to a human-readable format

    Arguments
    ---------
    timedelta: Optional[`timedelta`]
        A `timedelta` object to convert
    seconds: Optional[`int`]
        The time in seconds

    Raises
    ------
    ValueError:
        You didn't provide either the time in seconds or a `timedelta` object to convert

    Returns
    -------
    humanize_timedelta: `str`
        The arguments in a human-readable format
    """

    try:
        obj = seconds if seconds is not None else timedelta.total_seconds()
    except AttributeError:
        raise ValueError("You must provide either a timedelta or a number of seconds")

    seconds = int(obj)
    periods = [
        ("year", "years", 60 * 60 * 24 * 365),
        ("month", "months", 60 * 60 * 24 * 30),
        ("day", "days", 60 * 60 * 24),
        ("hour", "hours", 60 * 60),
        ("minute", "minutes", 60),
        ("second", "seconds", 1),
    ]

    strings = []
    for period_name, plural_period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            if period_value == 0:
                continue
            unit = plural_period_name if period_value > 1 else period_name
            strings.append(f"{period_value} {unit}")

    return ", ".join(strings)


async def mobile(self: DiscordWebSocket):
    """
    Library override to allow for a mobile status on your bot.
    """
    payload = {
        "op": self.IDENTIFY,
        "d": {
            "token": self.token,
            "properties": {
                "$os": sys.platform,
                "$browser": "Discord iOS",
                "$device": "discord.py",
                "$referrer": "",
                "$referring_domain": "",
            },
            "compress": True,
            "large_threshold": 250,
            "v": 3,
        },
    }

    if self.shard_id is not None and self.shard_count is not None:
        payload["d"]["shard"] = [self.shard_id, self.shard_count]

    state = self._connection
    if state._activity is not None or state._status is not None:
        payload["d"]["presence"] = {
            "status": state._status,
            "game": state._activity,
            "since": 0,
            "afk": False,
        }

    if state._intents is not None:
        payload["d"]["intents"] = state._intents.value

    await self.call_hooks("before_identify", self.shard_id, initial=self._initial_identify)
    await self.send_as_json(payload)


async def setup(_):
    """
    Used to make this file loadable as an extension
    """


class PrintColours:
    """
    A group of formatting strings used to change the colour of the text in your terminal
    """

    PURPLE = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    WHITE = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


class Botcolours:
    """
    A group of commonly used colours (usually used on embeds)
    """

    red = 0xC0382B
    orange = 0xFF8000
    yellow = 0xFFFF00
    green = 0x2ECC70
    cyan = 0x09DFFF
    blue = 0x0000FF
    pink = 0xFF0080


class NewEmote(PartialEmoji):
    """
    A subclass of `PartialEmoji` that allows an instance to be created from a name
    """

    @classmethod
    def from_name(cls, name: str):
        emoji_name = re.sub("|<|>", "", name)
        a, name, id = emoji_name.split(":")
        return cls(name=name, id=int(id), animated=bool(a))


class Confirm(View):
    """
    Pre-defined `View` class used to prompt the user for a yes/no confirmation

    Arguments
    ---------
    owner: `User`
        The user being prompted. They will be the one in control of this menu

    Attributes
    ----------
    choice: `bool`
        The choice that the user picked.
    interaction: `Interaction`
        The (unresponded) `Interaction` object from the user's button click.
    """

    def __init__(self, owner: User):
        self.choice = False
        self.interaction: Interaction = None
        self.owner = owner
        self.original_message: InteractionMessage = None

        super().__init__(timeout=120)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user != self.owner:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            c.disabled = True

        try:
            await self.original_message.edit(view=self)

        except discord.HTTPException:
            pass

        self.stop()

    @button(label="ye")
    async def ye(self, interaction: Interaction, btn: Button):
        for c in self.children:
            c.disabled = True

        btn.style = discord.ButtonStyle.success
        self.choice = True
        self.interaction = interaction
        return self.stop()

    @button(label="nu")
    async def nu(self, interaction: Interaction, btn: Button):
        for c in self.children:
            c.disabled = True

        btn.style = discord.ButtonStyle.success
        self.interaction = interaction
        return self.stop()


class BaseGameView(View):
    """
    A subclass of `View` that reworks the timeout logic
    """

    async def _scheduled_task(self, item: Item, interaction: Interaction):
        try:
            allow = await self.interaction_check(interaction, item)
            if allow is False:
                return

            if allow is not None:
                self._refresh_timeout()

            if item._provided_custom_id:
                await interaction.response.defer()

            await item.callback(interaction)
            if not interaction.response._responded:
                await interaction.response.defer()
        except Exception as e:
            return await self.on_error(e, item, interaction)


def emojiclass(cls: Type[Any]):
    with open("config/emojis.json", "r") as f:
        emojis: Dict[str, str] = json.load(f)

    for k, v in emojis.items():
        setattr(cls, k, v)

    return cls


@emojiclass
class BotEmojis:
    pass
