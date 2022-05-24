import asyncio
import copy
import time
import traceback
from itertools import cycle
from typing import List

import discord
from discord import ui, Interaction
from discord.app_commands import CheckFailure, errors, command, describe
from discord.ext import commands

from bot import NotGDKID, BotEmojis
from config.utils import BaseGameView, Botcolours, Confirm


class MaxConcurrencyReached(CheckFailure):
    ...


class DiagonalDirection:
    LEFT = 1
    RIGHT = 2


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
            self.emoji = BotEmojis.C4_RED

        elif self.number == 1:
            self.emoji = BotEmojis.C4_YELLOW

    def __repr__(self) -> str:
        return f"{self.name}#{self.discriminator}"


class Slot:
    def __init__(self, x: int, y: int, list_index: int) -> None:
        self.x = x
        self.y = y
        self.list_index = list_index
        self.occupant: Player | None = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} x={self.x} y={self.y}>"


class Game:
    def __init__(self, players: List[discord.User]):
        self.slots: List[Slot] = []
        self.players: List[Player] = [Player(players[i], i) for i in range(len(players))]
        self.turns = cycle(self.players)
        self.winner: Player = None
        self.moves = 0

        counter = 0
        for x in range(7):
            for y in range(6):
                self.slots.append(Slot(x, y, counter))
                counter += 1

    def drop_to_bottom(self, drop_column: int, player: Player):
        column = self._get_column(drop_column)
        if column[0].occupant:
            return

        for o in enumerate(column):
            i, s = o
            if i == 5 or column[i + 1].occupant:
                s.occupant = player
                self.moves += 1
                return

    def check_4(self) -> Player | None:
        def check_slot_list(slots: List[Slot] | None) -> bool:
            if not slots or len(slots) < 4:
                return False

            streak: List[Slot] = []
            streak_player = None
            for s in slots:
                if not s.occupant:
                    streak.clear()
                    streak_player = s.occupant
                    continue

                if s.occupant and s.occupant is not streak_player:
                    streak.clear()
                    streak.append(s)
                    streak_player = s.occupant
                    continue

                streak.append(s)

                if len(streak) >= 4:
                    self.winner = s.occupant
                    self.ws = streak
                    return True

            return False

        for i in range(7):
            co = self._get_column(i)

            if check_slot_list(co):
                return self.winner

        for i in range(6):
            ro = self._get_row(i)

            if check_slot_list(ro):
                return self.winner

        for i in range(-5, 7):
            diag_right = self._get_diagonal(DiagonalDirection.RIGHT, i)

            if check_slot_list(diag_right):
                return self.winner

        for i in range(11, -1, -1):
            diag_left = self._get_diagonal(DiagonalDirection.LEFT, i)

            if check_slot_list(diag_left):
                return self.winner

    def _get_slot(self, x: int, y: int) -> Slot | None:
        try:
            return [s for s in self.slots if s.x == x and s.y == y][0]

        except IndexError:
            return None

    def _get_column(self, x: int) -> List[Slot] | None:
        return [s for s in self.slots if s.x == x] or None

    def _get_row(self, y: int) -> List[Slot] | None:
        return [s for s in self.slots if s.y == y] or None

    def _get_diagonal(
        self,
        direction: DiagonalDirection,
        x: int | None = None,
    ) -> List[Slot] | None:
        diag: List[Slot] = []

        y = 0

        if (s := self._get_slot(x, y)) is not None:
            diag.append(s)

        for _ in range(6):
            y += 1
            if direction == DiagonalDirection.RIGHT:
                x += 1

            elif direction == DiagonalDirection.LEFT:
                x -= 1

            if (s := self._get_slot(x, y)) is not None:
                diag.append(s)

        return diag or None


class GameView(BaseGameView):
    def __init__(
        self,
        interaction: Interaction,
        players: List[discord.User],
        client: NotGDKID = None,
    ) -> None:
        self.interaction: Interaction = interaction
        self.client = client or interaction.client
        self.hovering = 1
        self.timed_out = 0
        self.moved_at = time.time()
        self.turn_timeout = 30

        self.game = Game(players)

        self.turn = next(self.game.turns)
        self.original_message: discord.Message = None

        self.client._connect4_games.append(self)

        super().__init__(timeout=None)

        self.client.loop.create_task(self.turn_timeout_loop())

    async def turn_timeout_loop(self):
        while hasattr(self, "game"):
            try:
                before_slots = self.game.slots.copy()
                before_turn = copy.copy(self.turn)
                before_moves = copy.copy(self.game.moves)

                while (time.time() - self.moved_at) < self.turn_timeout:
                    if not hasattr(self, "game"):
                        return

                    await asyncio.sleep(1)

                if before_slots == self.game.slots and self.turn == before_turn and before_moves == self.game.moves:
                    await self.on_turn_timeout()
                    self.timed_out += 1

                else:
                    self.timed_out = 0

            except AttributeError:
                break

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if interaction.user not in self.game.players:
            await interaction.response.send_message("its not your game", ephemeral=True)
            return False

        return True

    async def on_game_timeout(self) -> None:
        for c in self.children:
            c.disabled = True

        await self.original_message.edit(f"ok i think you both just {BotEmojis.PEACE}'d out on me", view=None)

        self.stop()

    async def on_win(self, winner: Player) -> None:
        await self.update_board(message=self.original_message)
        return self.stop()

    async def on_turn_timeout(self) -> None:
        self.moved_at += self.turn_timeout

        if self.timed_out > 3:
            await self.on_game_timeout()

        if len([s.occupant for s in self.game._get_column(self.hovering - 1) if s.occupant is not None]) == 6:
            if self.hovering < 7:
                self.hovering += 1

            else:
                self.hovering = 1
        self.game.drop_to_bottom(self.hovering - 1, self.turn)

        self.turn = next(self.game.turns)

        if None not in [s.occupant for s in self.game.slots]:
            for c in self.children:
                c.disabled = True

            await self.update_board(message=self.original_message, tie=True)
            return self.stop()

        winner = self.game.check_4()
        if winner:
            return await self.on_win(winner)

        else:
            await self.update_board(message=self.original_message)

    def stop(self):
        self.client._connect4_games.pop(self.client._connect4_games.index(self))
        del self.game

        return super().stop()

    async def update_board(
        self,
        interaction: Interaction | None = None,
        message: discord.InteractionMessage | None = None,
        drop: bool = False,
        gave_up: bool = False,
        tie: bool = False,
    ):
        if drop and interaction:
            add = time.time() - self.moved_at
            self.moved_at += add

        if not self.game.winner:
            content = "".join(
                [
                    f"{self.turn.mention} your turn! you have `{self.turn_timeout}` seconds to make a move\n",
                    "(or else im dropping your piece wherever the pointer is)\n\n",
                ]
            )

        else:
            for player in self.game.players:
                if player.id != self.game.winner.id:
                    content = f"{player.mention} you lose. imagine losing\n\n"
                    break

        if gave_up:
            content = f"{interaction.user.mention} gave up lol\n\n"

        if tie:
            content = "its a tie ¯\_(ツ)_/¯\n\n"

        content += "".join(
            [
                BotEmojis.BLANK * (self.hovering - 1),
                f"{BotEmojis.ARROW_DOWN}\n" if not self.game.winner and not gave_up and not tie else "\n",
                BotEmojis.C4_LINE_NEUTRAL * (self.hovering - 1),
                BotEmojis.C4_LINE_RED
                if self.turn.number == 0 and not self.game.winner and not gave_up and not tie
                else BotEmojis.C4_LINE_YELLOW
                if self.turn.number == 1 and not self.game.winner and not gave_up and not tie
                else BotEmojis.C4_LINE_NEUTRAL,
                BotEmojis.C4_LINE_NEUTRAL * (7 - self.hovering),
                "\n",
            ]
        )

        for i in range(6):
            ro = self.game._get_row(i)

            for s in ro:
                try:
                    content += s.occupant.emoji

                except Exception:
                    content += BotEmojis.BLANK

            content += "\n"

        content += "".join(
            [
                BotEmojis.C4_LINE_NEUTRAL * (self.hovering - 1),
                BotEmojis.C4_LINE_RED
                if self.turn.number == 0 and not self.game.winner and not gave_up and not tie
                else BotEmojis.C4_LINE_YELLOW
                if self.turn.number == 1 and not self.game.winner and not gave_up and not tie
                else BotEmojis.C4_LINE_NEUTRAL,
                BotEmojis.C4_LINE_NEUTRAL * (7 - self.hovering),
                "\n",
            ]
        )

        if not self.game.winner:
            reds = [
                BotEmojis.C4_RED_LEFT,
                BotEmojis.C4_RED_RIGHT,
                BotEmojis.C4_RED_DROP,
                BotEmojis.C4_RED_LEFTER,
                BotEmojis.C4_RED_RIGHTER,
            ]
            yellows = [
                BotEmojis.C4_YELLOW_LEFT,
                BotEmojis.C4_YELLOW_RIGHT,
                BotEmojis.C4_YELLOW_DROP,
                BotEmojis.C4_YELLOW_LEFTER,
                BotEmojis.C4_YELLOW_RIGHTER,
            ]

            if self.turn.number == 0:
                to_use = reds
            else:
                to_use = yellows

            self.move_left.emoji = to_use[0]
            self.move_right.emoji = to_use[1]
            self.drop_piece.emoji = to_use[2]
            self.move_lefter.emoji = to_use[3]
            self.move_righter.emoji = to_use[4]

        if interaction:
            try:
                return await interaction.response.edit_message(content=content, view=self)

            except discord.InteractionResponded:
                return await interaction.followup.edit_message(
                    message_id=self.original_message.id, content=content, view=self
                )

        elif message and not interaction:
            return await self.original_message.edit(content=content, view=self)

    @ui.button(emoji=BotEmojis.C4_RED_LEFT)
    async def move_left(self, interaction: Interaction, btn: ui.Button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("wait your turn", ephemeral=True)

        self.timed_out = 0
        if not self.hovering > 1:
            self.hovering = 7

        elif self.hovering > 1:
            self.hovering -= 1

        await self.update_board(interaction=interaction)

    @ui.button(emoji=BotEmojis.C4_RED_RIGHT)
    async def move_right(self, interaction: Interaction, btn: ui.Button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("wait your turn", ephemeral=True)

        self.timed_out = 0
        if not self.hovering < 7:
            self.hovering = 1

        elif self.hovering < 7:
            self.hovering += 1

        await self.update_board(interaction=interaction)

    @ui.button(emoji=BotEmojis.C4_RED_LEFTER, row=1)
    async def move_lefter(self, interaction: Interaction, btn: ui.Button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("wait your turn", ephemeral=True)

        self.timed_out = 0
        self.hovering = 1

        await self.update_board(interaction=interaction)

    @ui.button(emoji=BotEmojis.C4_RED_RIGHTER, row=1)
    async def move_righter(self, interaction: Interaction, btn: ui.Button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("wait your turn", ephemeral=True)

        self.timed_out = 0
        self.hovering = 7

        await self.update_board(interaction=interaction)

    @ui.button(label="\u200b", disabled=True)
    async def separator(*args):
        ...

    @ui.button(emoji=BotEmojis.C4_RED_DROP, style=discord.ButtonStyle.secondary)
    async def drop_piece(self, interaction: Interaction, btn: ui.Button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("wait your turn", ephemeral=True)

        if self.game._get_column(self.hovering - 1)[0].occupant:
            return

        self.timed_out = 0
        self.game.drop_to_bottom(self.hovering - 1, self.turn)
        self.turn = next(self.game.turns)

        if None not in [s.occupant for s in self.game.slots]:
            for c in self.children:
                c.disabled = True

            await self.update_board(interaction=interaction)
            return self.stop()

        winner = self.game.check_4()
        if winner:
            for c in self.children:
                c.disabled = True

            await self.update_board(interaction=interaction, drop=True)
            return self.stop()

        else:
            await self.update_board(interaction=interaction, drop=True)

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
            await view.interaction.followup.send("kden", ephemeral=True)

        elif not self.is_finished():
            for c in self.children:
                c.disabled = True

            await self.update_board(interaction=interaction, gave_up=True)
            self.stop()


class ConnectFour(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Connect4 cog loaded")

    @command(name="connect4")
    @describe(opponent="the person you wanna play against")
    async def connect4(self, interaction: Interaction, opponent: discord.User):
        """play connect4 with someone"""

        for game in self.client._connect4_games:
            game: GameView
            if interaction.user.id in [u.id for u in game.game.players]:
                raise MaxConcurrencyReached

        if opponent.id == interaction.user.id or opponent.bot:
            return await interaction.response.send_message("aw hell nah", ephemeral=True)

        view = Confirm(opponent)
        embed = discord.Embed(
            title="connect 4",
            description=f"{interaction.user.mention} wants to play connect 4 with you, accept game?",
            colour=0x09DFFF,
        )

        await interaction.response.send_message(opponent.mention, embed=embed, view=view)
        view.original_message = (
            msg := await interaction.channel.fetch_message((await interaction.original_message()).id)
        )

        await view.wait()
        await view.interaction.response.defer()

        if not view.choice:
            embed = msg.embeds[0].copy()
            embed.colour = Botcolours.red
            await msg.edit(embed=embed, view=view)
            return

        for game in self.client._connect4_games:
            game: GameView
            if interaction.user.id in [u.id for u in game.game.players]:
                author_game = game.original_message.jump_url

                embed = msg.embeds[0].copy()
                embed.colour = Botcolours.red
                embed.description = (
                    "you already have a game going on"
                    f"\n{'[jump to game](<' + author_game + '>)' if author_game is not None else ''}"
                )
                await msg.edit(embed=embed, view=view)
                raise MaxConcurrencyReached

        view = GameView(interaction, [opponent, interaction.user])

        content = "".join(
            [
                f"{view.turn.mention} your turn! you have `{view.turn_timeout}` seconds to make a move\n",
                "(or else im dropping your piece wherever the pointer is)\n\n",
                BotEmojis.BLANK * (view.hovering - 1),
                f"{BotEmojis.ARROW_DOWN}\n",
                BotEmojis.C4_LINE_NEUTRAL * (view.hovering - 1),
                BotEmojis.C4_LINE_RED
                if view.turn.number == 0
                else BotEmojis.C4_LINE_YELLOW
                if view.turn.number == 1
                else BotEmojis.C4_LINE_NEUTRAL,
                BotEmojis.C4_LINE_NEUTRAL * (7 - view.hovering),
                "\n",
            ]
        )

        for i in range(6):
            ro = view.game._get_row(i)

            for s in ro:
                try:
                    content += s.occupant.emoji

                except Exception:
                    content += BotEmojis.BLANK

            content += "\n"

        content += "".join(
            [
                BotEmojis.C4_LINE_NEUTRAL * (view.hovering - 1),
                BotEmojis.C4_LINE_RED
                if view.turn.number == 0
                else BotEmojis.C4_LINE_YELLOW
                if view.turn.number == 1
                else BotEmojis.C4_LINE_NEUTRAL,
                BotEmojis.C4_LINE_NEUTRAL * (7 - view.hovering),
                "\n",
            ]
        )

        await interaction.followup.edit_message(message_id=msg.id, embed=None, content=content, view=view)
        view.original_message = msg

        await view.wait()

    @connect4.error
    async def connect4_error(self, interaction: Interaction, error: errors.AppCommandError):
        print("".join(traceback.format_exc()))
        if isinstance(error, MaxConcurrencyReached):
            author_game = None

            for gameview in self.client._connect4_games:
                gameview: GameView

                if interaction.user.id in [p.id for p in gameview.game.players]:
                    author_game = gameview.original_message.jump_url
                    break

            return await interaction.response.send_message(
                "you already have a game going on"
                f"\n{'[jump to game](<' + author_game + '>)' if author_game is not None else ''}",
                ephemeral=True,
            )


async def setup(client: NotGDKID):
    await client.add_cog(ConnectFour(client=client))
