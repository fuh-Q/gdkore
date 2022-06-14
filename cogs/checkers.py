from __future__ import annotations

import traceback
from itertools import cycle
from typing import Dict, List, Tuple, Type

import discord
from discord import Interaction, ui
from discord.app_commands import CheckFailure, command, describe, errors
from discord.ext import commands

from bot import BotEmojis, NotGDKID
from config.utils import (BaseGameView, Botcolours, Confirm,
                          MaxConcurrencyReached)

MOVEMENTS: List[str] = ["NORTHWEST", "NORTHEAST", "SOUTHWEST", "SOUTHEAST"]


def directional_button(direction: str) -> Type[ui.Button]:
    class cls(ui.Button):
        @property
        def view(self) -> Game:
            return self._view

        def __init__(self, view: Game) -> None:
            self._view = view

            row = 1 if direction.startswith("north") else 2
            emoji = getattr(BotEmojis, f"CHECKERS_RED_{direction.upper()}")

            super().__init__(
                row=row,
                disabled=True,
                emoji=emoji,
            )

        async def callback(self, interaction: Interaction) -> None:
            if interaction.user.id != self.view.turn.id:
                return await interaction.response.send_message(
                    "wait your turn", ephemeral=True
                )

            piece = self.view.selected or self.view.logic.jumping_piece
            self.view.logic.move_piece(
                piece,
                direction.upper(),
                jump_confirm=(
                    True if piece is self.view.logic.jumping_piece else False
                ),
            )

            if self.view.logic.jumping_piece is None:
                self.view.turn = next(self.view.logic.turns)

            if loser := self.view.logic.check_loser():
                self.view.logic.loser = loser

            await self.view.update_ui(interaction)

    return cls


class Player(discord.User):
    __slots__ = ("user", "number", "emoji_colour")

    def __init__(self, original: discord.User, number: int):
        self.name = original.name
        self.id = original.id
        self.discriminator = original.discriminator
        self.bot = original.bot

        self.user = original

        self.number = number

        self.emoji_colour: str = "RED" if number == 0 else "BLUE"

    def __repr__(self) -> str:
        return f"{self.name}#{self.discriminator}"


class Slot:
    def __init__(self, x: int, y: int, list_index: int, null: bool) -> None:
        self.x = x
        self.y = y
        self.null = null
        self.list_index = list_index
        self.occupant: Player | None = None

        self.piece: Piece | None = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} x={self.x} y={self.y}>"


class Piece:
    def __init__(self, logic: Logic, owner: Player, x: int, y: int):
        self.owner = owner
        self.x = x
        self.y = y
        self.king: bool = False

        self.logic: Logic = logic
        self.slot: Slot = self.logic._get_slot(x, y)

        if owner.number == 0:
            self.valid_directions = ["NORTHWEST", "NORTHEAST"]
            self.emoji: str = BotEmojis.CHECKERS_RED

        else:
            self.valid_directions = ["SOUTHWEST", "SOUTHEAST"]
            self.emoji: str = BotEmojis.CHECKERS_BLUE


class Logic:
    def __init__(self, players: List[discord.User], view: Game) -> None:
        self.slots: List[Slot] = []
        self.pieces: List[Piece] = []
        self.view: Game = view

        self.jumping_piece: Piece | None = None
        self.jumped_counter: int = 0

        self.users = players
        self.players = [Player(players[i], i) for i in range(len(players))]

        self.turns: cycle[Player] = cycle(self.players)
        self.loser: Player | None = None
        self.challenger, self.opponent = self.players

        # board generation
        counter = 0
        for y in range(8):
            for x in range(8):
                null = y % 2 == 0 and x % 2 == 0 or y % 2 == 1 and x % 2 == 1

                self.slots.append(Slot(x, y, counter, null))
                counter += 1

        for sl in self.slots[:24]:
            if not sl.null:
                piece = Piece(self, self.opponent, sl.x, sl.y)
                sl.occupant = piece.owner
                sl.piece = piece
                self.pieces.append(piece)

        for sl in self.slots[-24:]:
            if not sl.null:
                piece = Piece(self, self.challenger, sl.x, sl.y)
                sl.occupant = piece.owner
                sl.piece = piece
                self.pieces.append(piece)

    def verify_directions(
        self, piece: Piece, *, jump_only: bool = False
    ) -> Dict[str, bool]:
        directions: Dict[str, bool] = {}
        for i in MOVEMENTS:
            directions[i] = False

        for direction in directions.keys():
            op_x, op_y = self._resolve_direction(direction)

            directions[direction] = (
                True
                if (sl := self._get_slot(piece.x - op_x, piece.y - op_y)) is not None
                and (
                    sl.occupant is None
                    and not jump_only
                    or self.check_jump(piece, direction)  # no one occupying it
                )  # or occupied but we can jump it
                else False
            )

        if not piece.king:
            if piece.owner is self.opponent:
                directions["NORTHWEST"] = False
                directions["NORTHEAST"] = False

            if piece.owner is self.challenger:
                directions["SOUTHEAST"] = False
                directions["SOUTHWEST"] = False

        return directions

    def check_jump(self, piece: Piece, direction: str) -> bool:
        op_x, op_y = self._resolve_direction(direction)

        sl1 = self._get_slot(piece.x - op_x, piece.y - op_y)
        sl2 = self._get_slot(piece.x - op_x * 2, piece.y - op_y * 2)

        if sl2 and not sl2.occupant and sl1.occupant and sl1.occupant != piece.owner:
            return True

        else:
            return False

    def check_loser(self) -> Player | None:
        if len(self.pieces) > 12:
            return

        challenger = sum(pi.owner == self.challenger for pi in self.pieces)
        opponent = sum(pi.owner == self.opponent for pi in self.pieces)

        if opponent == 0:
            return self.opponent

        elif challenger == 0:
            return self.challenger

        else:
            return

    def move_piece(
        self, piece: Piece, direction: str, *, jump_confirm: bool = False
    ) -> None:
        op_x, op_y = self._resolve_direction(direction)
        if not jump_confirm:
            jump_confirm = self.check_jump(piece, direction)

        (old := self._get_slot(piece.x, piece.y)).occupant = None
        old.piece = None

        (
            new := self._get_slot(
                piece.x - op_x * (2 if jump_confirm else 1),
                piece.y - op_y * (2 if jump_confirm else 1),
            )
        ).occupant = piece.owner

        new.piece = piece
        piece.slot = new

        piece.x = new.x
        piece.y = new.y

        if jump_confirm:
            self.jumping_piece = piece
            self.jumped_counter += 1
            jumped = self._get_slot(old.x - op_x, old.y - op_y)
            jumped.occupant = None
            self.pieces.remove(jumped.piece)

        if new.y in (0, 7) and not piece.king:
            self._evolve_piece(piece)

        self.view.selected = None

    def _evolve_piece(self, piece: Piece) -> Piece:
        piece.king = True

        if piece.owner.number == 0:
            piece.emoji = BotEmojis.CHECKERS_RED_KING

        else:
            piece.emoji = BotEmojis.CHECKERS_BLUE_KING

    def _resolve_direction(self, direction: str) -> Tuple[int, int]:
        ops: List[int, int] = []

        if direction == "NORTHWEST":
            ops = [1, 1]

        if direction == "NORTHEAST":
            ops = [-1, 1]

        if direction == "SOUTHEAST":
            ops = [-1, -1]

        if direction == "SOUTHWEST":
            ops = [1, -1]

        return tuple(ops)

    def _get_slot(self, x: int, y: int) -> Slot | None:
        try:
            return [s for s in self.slots if s.x == x and s.y == y][0]

        except IndexError:
            return None

    def _get_piece(self, x: int, y: int) -> Piece | None:
        try:
            return [p for p in self.pieces if p.x == x and p.y == y][0]

        except IndexError:
            return None


class Game(BaseGameView):
    children: List[ui.Select | ui.Button]
    northwest: ui.Button[Game]
    northeast: ui.Button[Game]
    southwest: ui.Button[Game]
    southeast: ui.Button[Game]
    client: NotGDKID = None

    def __init__(
        self,
        interaction: Interaction,
        players: List[discord.User],
    ) -> None:
        self.logic = Logic(players, self)

        self.interaction: Interaction = interaction
        self.client: NotGDKID = self.client or interaction.client
        self.selected: Piece | None = None

        self.timed_out: bool = False
        self.turn = next(self.logic.turns)
        self.original_message: discord.Message = None

        self.client._checkers_games.append(self)

        super().__init__(timeout=120)
        self.clear_items()

        self.piece_selector = PieceSelector(self)
        self.add_item(self.piece_selector)

        for move in MOVEMENTS:
            setattr(self, move.lower(), directional_button(move.lower())(self))
            self.add_item(getattr(self, move.lower()))

        self.separator = ui.Button(label="\u200b", disabled=True, row=1)
        self.add_item(self.separator)

        self.add_item(self.forfeit)

    # fmt: off
    def _generate_select_options(self) -> List[discord.SelectOption]:
        ALPHABET = ["A", "B", "C", "D", "E", "F", "G", "H"]

        options: List[discord.SelectOption] = sorted([
            discord.SelectOption(
                label=f"{ALPHABET[p.x]}{p.y + 1}",
                emoji=(
                    BotEmojis.CHECKERS_RED
                    if p.owner.number == 0 and not p.king
                    else BotEmojis.CHECKERS_RED_KING
                    if p.owner.number == 0 and p.king
                    else BotEmojis.CHECKERS_BLUE
                    if p.owner.number == 1 and not p.king
                    else BotEmojis.CHECKERS_BLUE_KING
                ),
                description=(
                    f"{'[king] ' if p.king else ''}"
                    f"{'red' if p.owner.number == 0 else 'blue'} piece"
                ),
                value=f"{p.x}{p.y}",
            ) for p in self.logic.pieces
            if p.owner is self.turn and p is not self.selected],
            key=lambda k: k.value[1],
            reverse=True if self.turn is self.logic.opponent else False,
        )

        return options

    def generate_board(self) -> str:
        TOP = "ㅤㅤ`Ａ Ｂ Ｃ Ｄ Ｅ Ｆ Ｇ Ｈ`\n"

        board = TOP + "\n".join([
            f"`{i}. `" + "".join([((
                sl.piece.emoji
                if self.selected is not sl.piece
                or self.logic.loser is not None
                or self.timed_out
                else ((
                    BotEmojis.CHECKERS_RED_SELECTED
                    if not sl.piece.king
                    else BotEmojis.CHECKERS_RED_KING_SELECTED
                ) if sl.piece.owner.number == 0
                else (
                    BotEmojis.CHECKERS_BLUE_SELECTED
                    if not sl.piece.king
                    else BotEmojis.CHECKERS_BLUE_KING_SELECTED
                ))) if sl.occupant is not None
                    else BotEmojis.SQ
                    if sl.null
                    else BotEmojis.BLANK
                ) for sl in self.logic.slots
                  if sl.y == i - 1])
            for i in range(1, 9)
        ])

        return board
    # fmt: on

    async def update_ui(self, interaction: Interaction | None = None) -> None:
        header = ""
        board = self.generate_board()

        if self.logic.loser:
            self.stop()

            if self.logic.check_loser():
                header = f"{self.logic.loser.mention} you lose. imagine losing"

            else:
                header = f"{self.logic.loser.mention} gave up lol"

            self.disable_all()

        elif self.timed_out:
            self.stop()

            header = f"looks like {self.turn.mention} {BotEmojis.PEACE}'d out on us"

            self.disable_all()

        elif self.logic.jumping_piece is not None:
            s = "" if self.logic.jumped_counter == 1 else "s"
            header = (
                f"{self.turn.mention} jumped `{self.logic.jumped_counter}` piece{s}!"
            )

            for c in self.children[:-1]:
                c.disabled = True

            directions = self.logic.verify_directions(
                self.logic.jumping_piece, jump_only=True
            )

            for direction, value in directions.items():
                if value is True:
                    btn: ui.Button = getattr(self, direction.lower())
                    btn.disabled = False

            if True not in directions.values():
                self.logic.jumping_piece = None
                self.logic.jumped_counter = 0
                self.turn = next(self.logic.turns)

                self.piece_selector.disabled = False

        # checking it again as it might've changed
        if (
            self.logic.jumping_piece is None
            and self.logic.loser is None
            and not self.timed_out
        ):
            header = (
                f"{self.turn.mention} your turn! you have `2 minutes` to make a move"
                + (f"\n\n{header}" if header else "")
            )

            self.piece_selector.options = self._generate_select_options()
            if not self.piece_selector.options:
                self.piece_selector.disabled = True
                self.piece_selector.options = [
                    discord.SelectOption(label="no", description="fuck off")
                ]
            else:
                self.piece_selector.disabled = False

            for o in enumerate(self.children[1:-2]):
                i, c = o

                c.disabled = True
                c.emoji = getattr(
                    BotEmojis, f"CHECKERS_{self.turn.emoji_colour}_{MOVEMENTS[i]}"
                )

            if self.selected is not None:
                for direction, value in self.logic.verify_directions(
                    self.selected
                ).items():
                    if value is True:
                        btn: ui.Button = getattr(self, direction.lower())
                        btn.disabled = False

        content = header + "\n\n" + board

        if interaction:
            if not interaction.response._responded:
                await interaction.response.edit_message(content=content, view=self)

            else:
                await interaction.followup.edit_message(
                    self.original_message.id,
                    content=content,
                    view=self,
                )

        else:
            await self.original_message.edit(content=content, view=self)

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if item.__class__.__name__ != "cls":
            return None

        if interaction.user not in self.logic.users:
            await interaction.response.send_message("its not your game", ephemeral=True)
            return False

        return True

    async def on_timeout(self) -> None:
        self.timed_out = True

        await self.update_ui()

    def stop(self) -> None:
        self.client._checkers_games.remove(self)

        return super().stop()

    @ui.button(emoji=BotEmojis.QUIT_GAME, style=discord.ButtonStyle.danger)
    async def forfeit(self, interaction: Interaction, btn: ui.Button):
        view = Confirm(interaction.user)
        embed = discord.Embed(
            title="are you sure you want to forfeit?",
            colour=0xC0382B,
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.original_message = await interaction.original_message()

        await view.wait()

        await view.interaction.response.edit_message(view=view)
        if not view.choice:
            return await view.interaction.followup.send("kden", ephemeral=True)

        if not self.is_finished():
            self.disable_all()

            if interaction.user.id == self.logic.opponent.id:
                self.logic.loser = self.logic.opponent

            else:
                self.logic.loser = self.logic.challenger

            return await self.update_ui(interaction)


class PieceSelector(ui.Select):
    @property
    def view(self) -> Game:
        return self._view

    def __init__(self, view: Game) -> None:
        self._view = view
        options = self.view._generate_select_options()

        super().__init__(
            min_values=1,
            max_values=1,
            placeholder="pick a piece...",
            options=options,
        )

    async def callback(self, interaction: Interaction) -> ...:
        if interaction.user.id != self.view.turn.id:
            return await interaction.response.send_message(
                "wait your turn", ephemeral=True
            )

        x, y = map(lambda x: int(x), self.values[0])

        self.view.selected = self.view.logic._get_piece(x, y)

        await self.view.update_ui(interaction)


class Checkers(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Checkers cog loaded")

    @command(name="checkers")
    @describe(opponent="the person you wanna play against")
    async def checkers(self, interaction: Interaction, opponent: discord.User):
        """play checkers with someone"""

        for game in self.client._checkers_games:
            game: Game
            if interaction.user in game.logic.users:
                raise MaxConcurrencyReached(game.original_message.jump_url)

        if opponent.id == interaction.user.id or opponent.bot:
            return await interaction.response.send_message(
                "aw hell nah", ephemeral=True
            )

        view = Confirm(opponent)
        embed = discord.Embed(
            title="checkers",
            description=f"{interaction.user.mention} wants to play checkers with you, accept game?",
            colour=0x09DFFF,
        )

        await interaction.response.send_message(
            opponent.mention, embed=embed, view=view
        )
        view.original_message = (
            msg := await interaction.channel.fetch_message(
                (await interaction.original_message()).id
            )
        )

        await view.wait()
        await view.interaction.response.defer()

        if not view.choice:
            embed = msg.embeds[0].copy()
            embed.colour = Botcolours.red
            await msg.edit(embed=embed, view=view)
            return

        for game in self.client._checkers_games:
            game: Game
            if interaction.user in game.logic.users:
                author_game = game.original_message.jump_url

                embed = msg.embeds[0].copy()
                embed.colour = Botcolours.red
                embed.description = (
                    "you already have a game going on"
                    f"\n{'[jump to game](<' + author_game + '>)' if author_game is not None else ''}"
                )
                await msg.edit(embed=embed, view=view)
                return

        view = Game(interaction, [interaction.user, opponent])

        header = f"{view.turn.mention} your turn! you have `2 minutes` to make a move"
        board = view.generate_board()

        await interaction.followup.edit_message(
            msg.id, embed=None, content=header + "\n\n" + board, view=view
        )
        view.original_message = msg

        await view.wait()

    @checkers.error
    async def checkers_error(
        self, interaction: Interaction, error: errors.AppCommandError
    ):
        if isinstance(error, MaxConcurrencyReached):
            author_game = error.jump_url

            return await interaction.response.send_message(
                "you already have a game going on" f"\n[jump to game](<{author_game}>)",
                ephemeral=True,
            )


async def setup(client: NotGDKID):
    await client.add_cog(Checkers(client=client))
