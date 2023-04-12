import json
import pathlib
from typing import List

import asyncpg

from discord.ext import commands
from discord.app_commands import CheckFailure

no = f"[no](<https://discord.gg/ggZn8PaQed>)"
CHOICES = (
    f"***{no}.***",
    f"absolutely ***{no}t.***",
    f"eenie meenie miny moe,\n\n***{no}.***",
    f"hell ***{no}.***",
    f"***{no}pe.***",
    f"***{no}t*** happening."
    f"this is ***{no}t*** your menu.",
    f"i ***can{no}t.***",
    f"***{no}*** can do.",
    f"you shall ***{no}t*** pass.",
    f"***{no}h***",
    f"~~mo~~***{no}***~~poly~~",
    f"***{no}pe***, sorry.",
    f"i ***dun{no}***",
    f"roses are red\nviolets are blue\n\nthat's ***{no}t*** doing anything, since it wasn't for you.",
    f"1 2 3 4 5 6 7,\n\nthat isn't for you, so ***{no}thing's*** gonna happen.",
    f"a b c d e f g,\n\nit's ***{no}t*** happening, here's rick astley\n\nhttps://tenor.com/view/dance-moves-dancing-singer-groovy-gif-17029825"
)


class MaxConcurrencyReached(CheckFailure):
    """
    An error subclass typically for game commands
    Attributes
    ---------
    jump_url: `str`
        The jump url to the ongoing game's message
    """

    def __init__(self, jump_url: str) -> None:
        self.jump_url = jump_url


def get_extensions(prefix: str, /, *, get_global: bool = True) -> List[str]:
    """
    Returns a list of module strings to load as extensions.

    Arguments
    ---------
    prefix: `str`
        The prefix for the cogs folder to iterate through.
    get_global: `bool`
        Whether or not to return extensions in the global_cogs folder. Defaults to `True`.

    Returns
    -------
    get_extensions: `List[str]`
        A list of strings in Python module format.
    """

    def _inner(pre: str):
        if pre == "global_" and not get_global:
            return []

        return [
            ".".join(path.parts).removesuffix(".py")
            for path in pathlib.Path(f"{pre}cogs").rglob("[!_]*.py")
            if not path.is_dir()
        ]

    prefix += "_"

    return [*_inner(prefix.lstrip("_")), *_inner("global_")]


def get_member_count(client: commands.Bot) -> int:
    """
    Gets the total count of members the bot can see. Useful when you don't have `Intents.members` enabled.

    Arguments
    ---------
    client: `Bot`
        The bot to get the member count of.

    Returns
    -------
    get_member_count: `int`
        The total amount of members.
    """

    return sum([guild.member_count for guild in client.guilds])  # type: ignore


async def db_init(conn: asyncpg.Connection) -> None:
    """
    Sets up my personally preferred codecs for select types in our PostgreSQL connection.
    """

    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
