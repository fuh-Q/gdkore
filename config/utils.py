import datetime
import re
import sys
from typing import Optional, SupportsInt, Union

import discord
from discord.ext import commands

try:
    from bot import BanBattler
except ImportError:
    pass

from hc_bot import HeistingCultBot

CHOICES = [
    "No u",
    "You are not the chosen one",
    "Don't think you can use this menu mate",
    "`button.exe` has crashed... only on you",
    "Clickrolled\n\nhttps://tenor.com/view/dance-moves-dancing-singer-groovy-gif-17029825",
    "Couldn't verify that you can use this menu!",
    "Roses are red\nViolets are blue\nAy hol up you can't use this menu",
    "**HEY YOU**\n\n**I KNOW YOU AREN'T THE CONTROLLER OF THIS MENU. I'M WATCHING**",
    "Woah there! You can't go around trying to control other people's paginator sessions!! That's illegal!!!!",
    "Can I see your non-existent proof that you have control over this paginator?",
    "Nope, just... *no*",
    "~~*Pressing another button will get you banned*~~ **ahem** what?",
    "Get your own paginator session instead of trying to freeload on others!!",
]


def get_member_count(client: commands.Bot) -> int:
    return sum([guild.member_count for guild in client.guilds])


def get_invite_link(client: commands.Bot, permissions: int) -> str:
    return f"https://discord.com/api/oauth2/authorize?client_id={client.user.id}&permissions={permissions}&scope=bot%20applications.commands"


def all_casings(input_string: str):
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


async def mobile(self: discord.gateway.DiscordWebSocket):
    payload = {
        "op": self.IDENTIFY,
        "d": {
            "token": self.token,
            "properties": {
                "$os": sys.platform,
                "$browser": "Discord iOS",
                "$device": "pycord",
                "$referrer": "",
                "$referring_domain": ""
            },
            "compress": True,
            "large_threshold": 250,
            "v": 3
        }
    }
    
    if self.shard_id is not None and self.shard_count is not None:
        payload["d"]["shard"] = [self.shard_id, self.shard_count]
    
    state = self._connection
    if state._activity is not None or state._status is not None:
        payload["d"]["presence"] = {
            "status": state._status,
            "game": state._activity,
            "since": 0,
            "afk": False
        }
    
    if state._intents is not None:
        payload["d"]["intents"] = state._intents.value
    
    await self.call_hooks("before_identify", self.shard_id, initial=self._initial_identify)
    await self.send_as_json(payload)


class Botcolours:
    red = 0xC0382B
    orange = 0xFF8000
    yellow = 0xFFFF00
    green = 0x2ECC70
    cyan = 0x09DFFF
    blue = 0x0000FF
    pink = 0xFF0080


class BattlerCog(commands.Cog):
    def __init__(self, *args, **kwargs):
        self.client: Union[BanBattler, HeistingCultBot] = kwargs.pop("client")
        super().__init__(*args, **kwargs)

    @property
    def emoji(self):
        """Union[`str`, `Emoji`]: The emoji that will show up on the help page embed"""
        return self.__cog_emoji__

    @emoji.setter
    def emoji(self, emoji):
        self.__cog_emoji__ = emoji


class NewEmote(discord.PartialEmoji):
    @classmethod
    def from_name(cls, name):
        emoji_name = re.sub("|<|>", "", name)
        a, name, id = emoji_name.split(":")
        return cls(name=name, id=int(id), animated=bool(a))


class GuideEmbeds:
    @property
    def page_one(self) -> discord.Embed:
        return (
            discord.Embed(
                description="\n".join(
                    [
                        "Welcome to the Ban Battler Game Guide!",
                        "This is basically where all the bot's how-to's are gonna be located, so give it a good read, yeah?",
                        "",
                        "The guide is split up into 7 pages, with each page covering a different topic,",
                        "the topics and pages are:",
                        "",
                        "> `0.` ▏This page",
                        "> `1.` ▏What this is",
                        "> `2.` ▏Gamemodes",
                        "> `3.` ▏Options",
                        "> `4.` ▏Customization",
                        "> `5.` ▏Syntax",
                        "> `6.` ▏Miscellaneous",
                    ]
                ),
                color=Botcolours.cyan,
            )
            .set_footer(
                text="Click the buttons to go to their respective pages\nIf they're aren't buttons or they don't respond, run the command again"
            )
            .set_author(
                name="Ban Battler Game Guide",
                icon_url="https://cdn.discordapp.com/attachments/760253777113514055/858464945834295336/moar_epic.png",
            )
        )

    @property
    def page_two(self) -> discord.Embed:
        return (
            discord.Embed(
                title="The Game",
                description="\n".join(
                    [
                        "Ban Battle Royale, is a simple and fun Discord event.",
                        "Not quite sure who invented it, but the first time I've heard about it",
                        "was in one of [SoundDrout](https://www.youtube.com/channel/UCh6ZuSSFebAtWJTldsLxTtQ)'s YouTube videos.",
                        "",
                        "Here's [the link](https://www.youtube.com/watch?v=Q9G9KoAgEdM&t=362s) to the video if you wanna watch it yourself,",
                        "it's pretty cool ig :/",
                        "",
                        "(If you don't know how a Ban Battle works just watch the video above)",
                    ]
                ),
                color=Botcolours.cyan,
            )
            .set_footer(text=f"1/6")
            .set_author(
                name="Ban Battler Game Guide",
                icon_url="https://cdn.discordapp.com/attachments/760253777113514055/858464945834295336/moar_epic.png",
            )
        )

    @property
    def page_three(self) -> discord.Embed:
        return (
            discord.Embed(
                title="Gamemodes",
                description="\n".join(
                    [
                        "There are currently 3 gamemodes at this time:",
                        "",
                        "> `classic :` The original game of Discord Ban Battles",
                        "> --> Everybody tries to ban each other at once",
                        "> --> Last person standing wins",
                        "> --> __WILL BAN PEOPLE__",
                        "",
                        "> `passive :` Similar to `classic` but with a few changes",
                        "> --> Everybody tries to *eliminate* each other at once",
                        "> --> last person standing wins",
                        "> --> __DOES NOT BAN ANYBODY__",
                        "",
                        "> `selfban :` Similar to `classic`, idea from Loic#6969",
                        "> --> Identical to `classic` HOWEVER:",
                        "> --> **When banning someone there is a chance that you end up banning youself**",
                        "",
                        "What gamemode should I play?",
                        "",
                        "> -- `classic` is recommended for small ban-battle dedicated servers",
                        "> -- `passive` is for servers that want to host games without a secondary server",
                        "",
                        f"Pick your gamemode in the `/game start` command (more on syntax later)",
                    ]
                ),
                color=Botcolours.cyan,
            )
            .set_footer(text=f"2/6")
            .set_author(
                name="Ban Battler Game Guide",
                icon_url="https://cdn.discordapp.com/attachments/760253777113514055/858464945834295336/moar_epic.png",
            )
        )

    @property
    def page_four(self) -> discord.Embed:
        return (
            discord.Embed(
                title="Options",
                description="\n".join(
                    [
                        "I also have options you can use in the command",
                        "to modify the game even more.",
                        "Here's what I got:",
                        "",
                        "> `ping <role>` Ping a role for the event",
                        "> `req <role>` Unlock the channel for only this role",
                        "",
                        "**__Command Examples__**",
                        "",
                        f"> `/game start classic                  `",
                        f"> `/game start classic req @Booster     `",
                        f"> `/game start passive ping             `",
                    ]
                ),
                color=Botcolours.cyan,
            )
            .set_footer(text=f"3/6")
            .set_author(
                name="Ban Battler Game Guide",
                icon_url="https://cdn.discordapp.com/attachments/760253777113514055/858464945834295336/moar_epic.png",
            )
        )

    @property
    def page_five(self) -> discord.Embed:
        return (
            discord.Embed(
                title="Customization",
                description="\n".join(
                    [
                        "Probably the more exciting part of this bot",
                        "There are a lot of changable settings, so let's get",
                        "right into it.",
                        "",
                        "> - `GameStarter :` The role that the hosts have, like an Event Manager role.",
                        "> Having this role allows the user to start Ban Battle games",
                        "",
                        "> - `TimeToJoin :` The time the bot waits for people to click the reaction to join",
                        "> the game. Minimum is 10 seconds, and maximum is 120 seconds.",
                        "> Note that while setting this, you are only allowed to input whole integers",
                        "",
                        "> - `GameTimeout :` The amount of time the bot wait's for someone to be",
                        '> eliminated before considering the game "dead" and ending it; Minimum is 60 seconds',
                        "> maximum is 600 seconds" "",
                        "> - `PlayerRole :` **This is an incredibly important setting. All modes require**",
                        "> **this to be set. This is the role distributed to players after the join time is up**",
                        "> **to validate them as players.**",
                        "",
                        "> - `CustomEmoji :` The emoji the bot reacts with on the starting embed",
                        "> for people to join",
                        "",
                        "> - `SelfBanChance :` This setting is required to be set to play **SelfBan Mode**.",
                        '> It determines the chance of you "accidently" banning yourself',
                        "",
                        "> - `BanDM :` The message that gets DM'd to the user who got banned",
                        "",
                        "> - `SelfBanDM :` This is another SelfBan Mode setting. This is the message",
                        "> that gets DM'd to the user who got self-banned",
                        "",
                        "Extra bits & pieces:",
                        "",
                        "- The `BanDM` setting offers TagScript-like blocks that can be used",
                        "to represent certain objects, simply put them in your message",
                        "and I will convert them",
                        "",
                        "Those blocks include:",
                        "",
                        r"> `{banned_by}                ` - Whoever banned you",
                        r"> `{banned_by_id}             ` - The ID of whoever banned you",
                        r"> `{banned_by_name}           ` - The name of whoever banned you",
                        r"> `{banned_by_discriminator}  ` - The tag [`#1234`] of whoever banned you",
                        r"> `{banned_by_mention}        ` - Ping the member that banned you",
                        "",
                        r"- The `SelfBanDM` setting also includes these features,",
                        '**but follow "target" rather than "banned_by" (e.g. `{target_id}`)**,',
                        "representing the member you attemped to ban",
                    ]
                ),
                color=Botcolours.cyan,
            )
            .set_footer(text=f"4/6")
            .set_author(
                name="Ban Battler Game Guide",
                icon_url="https://cdn.discordapp.com/attachments/760253777113514055/858464945834295336/moar_epic.png",
            )
        )

    @property
    def page_six(self) -> discord.Embed:
        return (
            discord.Embed(
                title="Syntax",
                description="\n".join(
                    [
                        f"`/game start <gamemode> [ping] [role]`",
                        "",
                        "`<gamemode>` is obviously where you put your choice of gamemode (Page 2)",
                        "",
                        "`[ping]` and `[role]` are additional options with more info on Page 3",
                        "---------------------------------------------------------------",
                        "",
                        "`/bansettings [setting] [argument]`",
                        "",
                        "Running this command without arguments will simply display all your current game settings",
                        "",
                        "Auto-complete is provided with certain settings for the `[argument]` option",
                        "Specifying a `[setting]` without an `[argument]` will simply reset that setting",
                        "",
                        "Have fun!",
                    ]
                ),
                color=Botcolours.cyan,
            )
            .set_footer(text=f"5/6")
            .set_author(
                name="Ban Battler Game Guide",
                icon_url="https://cdn.discordapp.com/attachments/760253777113514055/858464945834295336/moar_epic.png",
            )
        )

    @property
    def page_seven(self) -> discord.Embed:
        return (
            discord.Embed(
                title="Miscellaneous",
                description="\n".join(
                    [
                        "__**User Permissions**__",
                        f"- `Manage Server` **or** `Game Starter` [`/bansettings`]",
                        "",
                        "__**Bot Permissions**__",
                        "- `Manage Channels`, `Manage Roles`, `Manage Roles`,",
                        "- `Add Reactions`, `Embed Links`, `Send Messages`,",
                        "- `Mention All Roles` (for `ping` option),",
                        "- `Ban Members` (for `classic` and `selfban` modes)",
                        "",
                        "__**Max Concurrency**__",
                        "- 1 use(s) per guild",
                        "",
                        "__**Cooldown**__",
                        "- 1 use(s) per 20 seconds",
                    ]
                ),
                color=Botcolours.cyan,
            )
            .set_footer(text=f"6/6")
            .set_author(
                name="Ban Battler Game Guide",
                icon_url="https://cdn.discordapp.com/attachments/760253777113514055/858464945834295336/moar_epic.png",
            )
        )
