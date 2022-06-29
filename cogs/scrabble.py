from __future__ import annotations

import random
from typing import Dict, List, Set, Tuple

import discord
from discord import Interaction
from discord.app_commands import (Choice, checks, choices, command, describe,
                                  errors)
from discord.ext import commands

from bot import NotGDKID
from config.utils import BaseGameView, BotEmojis

# fmt: off
POUCH: List[Tuple[str, int]] = [
    ("a", 1) * 9, ("b", 3) * 2, ("c", 3) * 2,
    ("d", 2) * 4, ("e", 1) * 12, ("f", 4) * 2,
    ("g", 2) * 3,("h", 4) * 2,("i", 1) * 9,
    ("j", 8) * 1,("k", 5) * 1,("l", 1) * 4,
    ("m", 3) * 2,("n", 1) * 6,("o", 1) * 8,
    ("p", 3) * 2,("q", 10) * 1,("r", 1) * 6,
    ("s", 1) * 4,("t", 1) * 6,("u", 1) * 4,
    ("v", 4) * 2,("w", 4) * 2,("x", 8) * 1,
    ("y", 4) * 2,("z", 10) * 1,(" ", 0) * 2,
]
# fmt: on


class Player(discord.User):
    __slots__ = ("user", "number", "hand", "points")

    def __init__(self, original: discord.User, number: int):
        self.name = original.name
        self.id = original.id
        self.discriminator = original.discriminator
        self.bot = original.bot

        self.user = original

        self.number = number
        self.points = 0
        self.hand: List[Tile] = []

    def __repr__(self) -> str:
        return f"{self.name}#{self.discriminator}"


class Slot:
    def __init__(self, x: int, y: int, list_index: int, null: bool) -> None:
        self.x = x
        self.y = y
        self.null = null
        self.list_index = list_index

        self.tile: Tile | None = None
        # uidijhguiejrfdbuisahweausidkn

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} x={self.x} y={self.y}>"


class Tile:
    def __init__(self, letter: str, point_value: int):
        self.letter = letter
        self.points = point_value

        self.slot: Slot | None = None


class Logic:
    def __init__(self, players: List[discord.User], view: Game) -> None:
        pouch = POUCH.copy()
        random.shuffle(pouch)

        self.pouch: List[Tile] = [
            Tile(pouch[i][0], pouch[i][1]) for i, t in enumerate(pouch)
        ]


class Game(BaseGameView):
    def __init__(
        self,
        players: List[discord.User],
        interaction: Interaction,
    ):
        self.client = self.client or interaction.client

        super().__init__(timeout=None)


class Scrabble(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Scrabble cog loaded")


async def setup(client: NotGDKID):
    await client.add_cog(Scrabble(client=client))
