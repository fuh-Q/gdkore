from itertools import cycle
from typing import Dict, List

import discord
from discord import Interaction, ui
from discord.ext import commands
from discord.app_commands import (
    command,
    describe,
    choices,
    checks,
    Choice,
    CheckFailure
)

from bot import NotGDKID

class MaxConcurrencyReached(CheckFailure):
    ...


class MoveDirection:
    NORTHWEST = 1
    NORTHEAST = 2
    SOUTHEAST = 3
    SOUTHWEST = 4


class Player(discord.User):
    __slots__ = ("user", "number", "emoji")

    def __init__(self, original: discord.User, number: int):
        self.name = original.name
        self.id = original.id
        self.discriminator = original.discriminator
        self.bot = original.bot

        self.user = original

        self.number = number
        if self.number == 0:
            self.emoji = "🔴"

        elif self.number == 1:
            self.emoji = "🔵"

    def __repr__(self) -> str:
        return f"{self.name}#{self.discriminator}"


class Slot:
    def __init__(self, x: int, y: int, list_index: int, null: bool) -> None:
        self.x = x
        self.y = y
        self.null = null
        self.list_index = list_index
        self.occupant: Player | None = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} x={self.x} y={self.y}>"


class Piece:
    def __init__(self, owner: Player, x: int, y: int):
        self.owner = owner
        self.x = x
        self.y = y
        self.king: bool = False
        
        if owner.number == 0:
            self.valid_directions = [MoveDirection.NORTHWEST, MoveDirection.NORTHEAST]
        
        else:
            self.valid_directions = [MoveDirection.SOUTHWEST, MoveDirection.SOUTHEAST]


class Game:
    def __init__(self, players: List[discord.User]) -> None:
        self.slots: List[Slot] = []
        self.pieces: List[Piece] = []
        self.turns = cycle(self.players)
        self.winner: Player = None
        self.challenger, self.opponent = [Player(players[i], i) for i in range(len(players))]
        
        # board generation
        counter = 0
        for y in range(8):
            for x in range(8):
                if (
                    y % 2 == 0 and x % 2 == 1
                    or y % 2 == 1 and x % 2 == 0
                ):
                    self.slots.append(Slot(x, y, counter, False))
                
                else:
                    self.slots.append(Slot(x, y, counter, False))
                
                counter += 1
        
        for sl in self.slots[:24]:
            if not sl.null:
                piece = Piece(self.challenger, sl.x, sl.y)
                sl.occupant = piece
                self.pieces.append(piece)
        
        for sl in self.slots[-24:]:
            if not sl.null:
                piece = Piece(self.opponent, sl.x, sl.y)
                sl.occupant = piece
                self.pieces.append(piece)
    
    def look_around(self, piece: Piece) -> Dict[int, Slot | None]:
        if piece.king:
            return {
                MoveDirection.NORTHWEST: self._get_slot(piece.x - 1, piece.y - 1),
                MoveDirection.NORTHEAST: self._get_slot(piece.x + 1, piece.y - 1),
                MoveDirection.SOUTHEAST: self._get_slot(piece.x + 1, piece.y + 1),
                MoveDirection.SOUTHWEST: self._get_slot(piece.x - 1, piece.y + 1),
            }
        
        if piece.owner == self.challenger:
            return {
                MoveDirection.NORTHWEST: self._get_slot(piece.x - 1, piece.y - 1),
                MoveDirection.NORTHEAST: self._get_slot(piece.x + 1, piece.y - 1),
            }
        
        if piece.owner == self.opponent:
            return {
                MoveDirection.SOUTHEAST: self._get_slot(piece.x + 1, piece.y + 1),
                MoveDirection.SOUTHWEST: self._get_slot(piece.x - 1, piece.y + 1),
            }
    
    def check_jump(self, piece: Piece, direction: MoveDirection) -> bool:
        if direction not in piece.valid_directions and not piece.king:
            return False
        
        surroundings = self.look_around(piece)
        if surroundings[direction].occupant == next(self.turns):
            if direction == MoveDirection.NORTHWEST:
                args = (piece.x - 2, piece.y - 2)
            
            if direction == MoveDirection.NORTHEAST:
                args = (piece.x + 2, piece.y - 2)
            
            if direction == MoveDirection.SOUTHEAST:
                args = (piece.x + 2, piece.y + 2)
            
            if direction == MoveDirection.SOUTHWEST:
                args = (piece.x - 2, piece.y + 2)
            
            sl = self._get_slot(*args)
            if not sl or sl and sl.occupant:
                return False
            
            if sl and not sl.occupant:
                return True
        
        return False
    
    def _get_slot(self, x: int, y: int) -> Slot | None:
        try:
            return [s for s in self.slots if s.x == x and s.y == y][0]

        except IndexError:
            return None


class Checkers(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Checkers cog loaded")


async def setup(client: NotGDKID):
    await client.add_cog(Checkers(client=client))
