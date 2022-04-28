import asyncio
import copy
import time
import traceback
from itertools import cycle
from typing import List

import discord
from discord import Interaction
from discord.app_commands import CheckFailure, command, describe
from discord.ext import commands

from bot import NotGDKID
from config.utils import Confirm


class MaxConcurrencyReached(CheckFailure):
    ...


class DiagonalDirection:
    LEFT = 1
    RIGHT = 2


class Player(discord.User):
    __slots__ = ("user", "number", "emoji")

    def __init__(self, original: discord.User, number: int):
        self._state = original._state
        self.name = original.name
        self.id = original.id
        self.discriminator = original.discriminator
        self.bot = original.bot

        self.user = original

        self.number = number
        if self.number == 0:
            self.emoji = "<:red:964710751149363210>"

        elif self.number == 1:
            self.emoji = "<:yellow:964710751103246346>"

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
        self.player_list: List[Player] = [Player(players[i], i) for i in range(len(players))]
        self.players: cycle[Player] = cycle(self.player_list)
        self.winner: Player | None = None
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

        counter = 0
        for s in column:
            if counter == 5 or column[counter + 1].occupant:
                s.occupant = player
                self.moves += 1
                return

            counter += 1

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


class GameView(discord.ui.View):
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

        self.turn = next(self.game.players)
        self.original_message: discord.Message = None

        if len(players) == 1:
            players.append(client.user)

        self.client._connect4_games.append(self)

        super().__init__(timeout=None)

        self.client.loop.create_task(self.turn_timeout_loop())

    async def _scheduled_task(self, item: discord.ui.Item, interaction: Interaction):
        try:
            allow = await self.interaction_check(interaction)
            if not allow:
                return

            if self.timeout:
                self.__timeout_expiry = time.monotonic() + self.timeout

            if item._provided_custom_id:
                await interaction.response.defer()

            await item.callback(interaction)
            if not interaction.response._responded:
                await interaction.response.defer()
        except Exception as e:
            return await self.on_error(e, item, interaction)

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

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user not in self.game.player_list:
            await interaction.response.send_message("its not your game", ephemeral=True)
            return False

        return True

    async def on_game_timeout(self) -> None:
        for c in self.children:
            c.disabled = True

        await self.original_message.edit("ok i think you both just <a:peace:951323779756326912> out on me", view=None)

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

        self.turn = next(self.game.players)

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
            for player in self.game.player_list:
                if player.id != self.game.winner.id:
                    content = f"{player.mention} you lose. imagine losing\n\n"
                    break

        if gave_up:
            content = f"{interaction.user.mention} gave up lol\n\n"

        if tie:
            content = "its a tie ¯\_(ツ)_/¯\n\n"

        content += "".join(
            [
                "<:Blank:864555461886214174>" * (self.hovering - 1),
                "<a:arrowdown:951720657509564417>\n" if not self.game.winner and not gave_up and not tie else "\n",
                "<:lineneutral:964754865626705950>" * (self.hovering - 1),
                "<:linered:964755893050810409>"
                if self.turn.number == 0 and not self.game.winner and not gave_up and not tie
                else "<:lineyellow:964755893063393361>"
                if self.turn.number == 1 and not self.game.winner and not gave_up and not tie
                else "<:lineneutral:964754865626705950>",
                "<:lineneutral:964754865626705950>" * (7 - self.hovering),
                "\n",
            ]
        )

        for i in range(6):
            ro = self.game._get_row(i)

            for s in ro:
                try:
                    content += s.occupant.emoji

                except Exception:
                    content += "<:Blank:864555461886214174>"

            content += "\n"

        content += "".join(
            [
                "<:lineneutral:964754865626705950>" * (self.hovering - 1),
                "<:linered:964755893050810409>"
                if self.turn.number == 0 and not self.game.winner and not gave_up and not tie
                else "<:lineyellow:964755893063393361>"
                if self.turn.number == 1 and not self.game.winner and not gave_up and not tie
                else "<:lineneutral:964754865626705950>",
                "<:lineneutral:964754865626705950>" * (7 - self.hovering),
                "\n",
            ]
        )

        if not self.game.winner:
            reds = ["<:redleft:964765364212863056>", "<:redright:964765364242243614>", "<:reddrop:964771745691213844> "]
            yellows = [
                "<:yellowleft:964765364259012608>",
                "<:yellowright:964765364212863059>",
                "<:yellowdrop:964771745653481532>",
            ]
            counter = 0
            for c in self.children[:-1]:
                if self.turn.number == 0:
                    c.emoji = reds[counter]

                elif self.turn.number == 1:
                    c.emoji = yellows[counter]

                counter += 1

        if interaction:
            try:
                return await interaction.response.edit_message(content=content, view=self)

            except discord.InteractionResponded:
                return await interaction.followup.edit_message(
                    message_id=self.original_message.id, content=content, view=self
                )

        elif message and not interaction:
            return await self.original_message.edit(content=content, view=self)

    @discord.ui.button(emoji="<:redleft:964765364212863056> ", style=discord.ButtonStyle.secondary)
    async def move_left(self, interaction: Interaction, btn: discord.ui.Button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("wait your turn", ephemeral=True)

        self.timed_out = 0
        if self.hovering > 1:
            self.hovering -= 1

        await self.update_board(interaction=interaction)

    @discord.ui.button(emoji="<:redright:964765364242243614> ", style=discord.ButtonStyle.secondary)
    async def move_right(self, interaction: Interaction, btn: discord.ui.Button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("wait your turn", ephemeral=True)

        self.timed_out = 0
        if self.hovering < 7:
            self.hovering += 1

        await self.update_board(interaction=interaction)

    @discord.ui.button(emoji="<:reddrop:964771745691213844> ", style=discord.ButtonStyle.secondary)
    async def drop_piece(self, interaction: Interaction, btn: discord.ui.Button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("wait your turn", ephemeral=True)

        if self.game._get_column(self.hovering - 1)[0].occupant:
            return

        self.timed_out = 0
        self.game.drop_to_bottom(self.hovering - 1, self.turn)
        self.turn = next(self.game.players)

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

    @discord.ui.button(emoji="<:bye:954097284482736128>", style=discord.ButtonStyle.danger)
    async def forfeit(self, interaction: Interaction, btn: discord.ui.Button):
        view = Confirm(interaction.user)
        embed = discord.Embed(
            title="are you sure you want to forfeit?",
            colour=0xC0382B,
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.original_message = await interaction.original_message()

        await view.wait()
        for c in view.children:
            c.disabled = True

        await view.interaction.response.edit_message(view=view)
        if not view.choice:
            await view.interaction.followup.send("kden", ephemeral=True)

        else:
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
        """play connect4 against someone"""

        for game in self.client._connect4_games:
            game: GameView
            if interaction.user.id in [u.id for u in game.game.player_list]:
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
            embed.colour = 0xC0382B
            await msg.edit(embed=embed, view=view)
            return

        view = GameView(interaction, [opponent, interaction.user])

        content = "".join(
            [
                f"{view.turn.mention} your turn! you have `{view.turn_timeout}` seconds to make a move\n",
                "(or else im dropping your piece wherever the pointer is)\n\n",
                "<:Blank:864555461886214174>" * (view.hovering - 1),
                "<a:arrowdown:951720657509564417>\n",
                "<:lineneutral:964754865626705950>" * (view.hovering - 1),
                "<:linered:964755893050810409>"
                if view.turn.number == 0
                else "<:lineyellow:964755893063393361>"
                if view.turn.number == 1
                else "<:lineneutral:964754865626705950>",
                "<:lineneutral:964754865626705950>" * (7 - view.hovering),
                "\n",
            ]
        )

        for i in range(6):
            ro = view.game._get_row(i)

            for s in ro:
                try:
                    content += s.occupant.emoji

                except Exception:
                    content += "<:Blank:864555461886214174>"

            content += "\n"

        content += "".join(
            [
                "<:lineneutral:964754865626705950>" * (view.hovering - 1),
                "<:linered:964755893050810409>"
                if view.turn.number == 0
                else "<:lineyellow:964755893063393361>"
                if view.turn.number == 1
                else "<:lineneutral:964754865626705950>",
                "<:lineneutral:964754865626705950>" * (7 - view.hovering),
                "\n",
            ]
        )

        await interaction.followup.edit_message(message_id=msg.id, embed=None, content=content, view=view)
        view.original_message = msg

        await view.wait()

    @connect4.error
    async def connect4_error(self, interaction: Interaction, error):
        print("".join(traceback.format_exc()))
        if isinstance(error, commands.MaxConcurrencyReached):
            author_game = None

            for gameview in self.client._connect4_games:
                gameview: GameView

                if gameview.game.player.id == interaction.user.id:
                    author_game = gameview.original_message.jump_url

            return await interaction.response.send_message(
                "you already have a game going on"
                f"\n{'[jump to game message](<' + author_game + '>)' if author_game is not None else ''}",
                ephemeral=True,
            )


async def setup(client: NotGDKID):
    await client.add_cog(ConnectFour(client=client))
