import json
import os
import pathlib
import sys
from typing import List

import asyncpg

from discord.ext import commands
from discord.app_commands import CheckFailure

CHOICES = [
    "no",
    "its not your menu",
    "don't think you can use this menu mate",
    "you cant use that menu... but you *can* watch rick roll\n\nhttps://tenor.com/view/dance-moves-dancing-singer-groovy-gif-17029825",
    "couldn't verify that you can use this menu!",
    "roses are red\nviolets are blue\nay hol up you can't use this menu",
    "can i see your non-existent proof that you have control over this paginator?",
]

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


def get_extensions(prefix: str | None = None, /, *, get_global: bool = True) -> List[str]:
    """
    Returns a list of module strings to load as extensions.

    Arguments
    ---------
    prefix: `str`
        The prefix for the cogs folder to iterate through. Will use process file name if omitted.
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

    if prefix is None:
        prefix = "".join(sub[-2:] if (sub := sys.argv[0].partition("_")) else "")
    else:
        prefix += "_"

    return [*_inner(prefix), *_inner("global_")]


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
