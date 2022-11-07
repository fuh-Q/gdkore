import json
import asyncpg
from discord.ext import commands


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
    return sum([guild.member_count for guild in client.guilds]) # type: ignore

async def db_init(conn: asyncpg.Connection):
    """
    Sets up my personally preferred codecs for select types in our PostgreSQL connection.
    """

    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
