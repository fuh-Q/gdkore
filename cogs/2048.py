import math
import traceback
from enum import Enum
from random import choice as c
from random import choices as ch
from random import randint as r
from typing import Iterable, List, Optional, Tuple

import discord
from discord import Embed, Interaction, InteractionMessage, SelectOption, ui
from discord.app_commands import (CheckFailure, Choice, Group, choices,
                                  command, describe)
from discord.ext import commands

from bot import BotEmojis, NotGDKID
from config.utils import (CHOICES, BaseGameView, Botcolours,
                          MaxConcurrencyReached, NewEmote)

weights = (90, 10)  # 2, 4

win_map = {
    2: 32,
    3: 1024,
    4: 2048,
}


class Directions(Enum):
    LEFT = 1
    UP = 2
    DOWN = 3
    RIGHT = 4


class DirectionEmotes:
    LEFT = NewEmote.from_name(BotEmojis.ARROW_LEFT)
    UP = NewEmote.from_name(BotEmojis.ARROW_UP)
    DOWN = NewEmote.from_name(BotEmojis.ARROW_DOWN)
    RIGHT = NewEmote.from_name(BotEmojis.ARROW_RIGHT)
    BYE = NewEmote.from_name(BotEmojis.QUIT_GAME)


class Block:
    def __init__(
        self,
        x: int,
        y: int,
        list_index: int,
        value: Optional[int] = 0,
    ) -> None:
        self.x = x
        self.y = y
        self.list_index = list_index
        self.value = value

        self.display = str(self.value)
        if self.display == "0":
            self.display = "\u200b"

        self.frozen: bool = False

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} x={self.x} y={self.y} value={self.value}>"

    def __str__(self) -> str:
        return f"{self.value}"


class Logic:
    def __init__(
        self,
        grid_size: Optional[int] = 4,
        blocks: Optional[List[Block]] = None,
        score: int = 0,
        moves: int = 0,
    ):
        self.blocks: List[Block] = blocks or []
        self.grid_size = grid_size
        self.new_block = None
        self.player: discord.User = None

        self.score = score
        self.moves = moves

        self._moved: bool = False
        self._won: bool = False

        if not blocks:
            counter = 0

            for ro in range(self.grid_size):
                for co in range(self.grid_size):
                    self.blocks.append(Block(co, ro, counter))
                    counter += 1

            first_coords = (r(0, self.grid_size - 1), r(0, self.grid_size - 1))
            second_coords = (r(0, self.grid_size - 1), r(0, self.grid_size - 1))
            while second_coords == first_coords:
                second_coords = (r(0, self.grid_size - 1), r(0, self.grid_size - 1))

            first_block = self._get_block(*first_coords)
            second_block = self._get_block(*second_coords)

            first_block.value = ch([2, 4], weights=weights, k=1)[0]
            second_block.value = ch([2, 4], weights=weights, k=1)[0]

            first_block.display = first_block.value
            second_block.display = second_block.value

        elif blocks:
            for b in self.blocks:
                if b.value == win_map[grid_size]:
                    self._won = True

    @classmethod
    def from_data(cls, data: Tuple[List[int], int, int]):
        blocks, score, moves = data
        new_blocks: List[Block] = []

        counter = 0
        grid_size = round(math.sqrt(len(blocks)))

        for y in range(grid_size):
            for x in range(grid_size):
                new_blocks.append(Block(x, y, counter, blocks[counter]))
                counter += 1

        return cls(grid_size, new_blocks, score, moves)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} player={self.player} grid_size={self.grid_size}>"

    def move(self, direction: Directions):
        og_blocks = [b.value for b in self.blocks.copy()]

        def modify_block(xy, xy2):
            block = self._get_block(*xy)
            if block.value > 0:
                block.display = str(block.value)

            next_block = self._get_block(*xy2)
            if next_block and next_block.value > 0:
                next_block.display = str(next_block.value)

            if block and not next_block:
                return

            if block.frozen or next_block.frozen:
                return

            if block.value == next_block.value or next_block.value == 0:
                if block.value == next_block.value and block.value != 0:
                    next_block.frozen = True

                next_block.value += block.value
                if next_block.frozen:
                    self.score += next_block.value

                block.value = 0
                block.display = "\u200b"

        if direction == Directions.DOWN:
            for _ in range(2):
                for i in range(self.grid_size - 1, -1, -1):
                    for n in range(self.grid_size):
                        modify_block((n, i), (n, i + 1))

            for i in range(self.grid_size):
                for n in range(self.grid_size):
                    modify_block((n, i), (n, i + 1))

        if direction == Directions.UP:
            for _ in range(2):
                for i in range(self.grid_size):
                    for n in range(self.grid_size):
                        modify_block((n, i), (n, i - 1))

            for i in range(self.grid_size - 1, -1, -1):
                for n in range(self.grid_size):
                    modify_block((n, i), (n, i - 1))

        if direction == Directions.RIGHT:
            for _ in range(2):
                for i in range(self.grid_size):
                    for n in range(self.grid_size - 1, -1, -1):
                        modify_block((n, i), (n + 1, i))

            for i in range(self.grid_size):
                for n in range(self.grid_size):
                    modify_block((n, i), (n + 1, i))

        if direction == Directions.LEFT:
            for _ in range(2):
                for i in range(self.grid_size):
                    for n in range(self.grid_size):
                        modify_block((n, i), (n - 1, i))

            for i in range(self.grid_size):
                for n in range(self.grid_size - 1, -1, -1):
                    modify_block((n, i), (n - 1, i))

        for block in self.blocks:
            block.frozen = False

        now_blocks = [b.value for b in self.blocks.copy()]
        for i in range(len(og_blocks)):
            if og_blocks[i] != now_blocks[i]:
                self._moved = True
                self.moves += 1
                break

    def check_loss(self, blocks: List[Block]) -> bool:
        if self._moved:
            empty_spaces = []
            for block in blocks:
                if block.value == 0:
                    empty_spaces.append(block)

            new: Block = c(empty_spaces)
            new_block = blocks[blocks.index(new)]
            new_block.value = ch([2, 4], weights=weights, k=1)[0]
            new_block.display = new_block.value
            self.new_block = new_block

        self._moved = False
        self.blocks = blocks

        empty_spaces = []
        for block in self.blocks:
            if block.value == 0:
                empty_spaces.append(block)

        if not empty_spaces:
            can_save = False
            for b in self.blocks:
                if (
                    (blok := self._get_block(b.x - 1, b.y)) is not None
                    and blok.value == b.value
                    or (blok := self._get_block(b.x, b.y - 1)) is not None
                    and blok.value == b.value
                    or (blok := self._get_block(b.x + 1, b.y)) is not None
                    and blok.value == b.value
                    or (blok := self._get_block(b.x, b.y + 1)) is not None
                    and blok.value == b.value
                ):
                    can_save = True

            if not can_save:
                return True

        return False

    def _get_row(
        self, row: int, iterable: Optional[Iterable[Block]] = None
    ) -> List[Block]:
        if not iterable:
            iterable = self.blocks

        o = []

        for b in iterable:
            if b.x == row:
                o.append(b)

        return o

    def _get_column(
        self, column: int, iterable: Optional[Iterable[Block]] = None
    ) -> List[Block]:
        if not iterable:
            iterable = self.blocks

        o = []

        for b in iterable:
            if b.y == column:
                o.append(b)

        return o

    def _get_block(
        self, x, y, iterable: Optional[Iterable[Block]] = None
    ) -> Optional[Block]:
        if not iterable:
            iterable = self.blocks

        for b in iterable:
            if b.x == x and b.y == y:
                return b

        return


class Game(BaseGameView):
    grid_size = 4

    def __init__(
        self,
        interaction: Interaction,
        grid_size: Optional[int] = None,
        blocks: Optional[List[int]] = None,
        score: int = 0,
        moves: int = 0,
        embed: Optional[Embed] = None,
        controls: List[str] = [],
        client: Optional[NotGDKID] = None,
    ):
        super().__init__(timeout=120)

        self.logic = (
            Logic.from_data((blocks, score, moves))
            if blocks is not None and grid_size is None
            else Logic(grid_size=grid_size)
        )

        setattr(self.logic, "player", interaction.user)

        self.interaction = interaction
        self.client: NotGDKID = client or interaction.client
        self.embed = embed

        self.original_message: Optional[InteractionMessage] = None

        self.controls: List[str] = controls or ["left", "up", "down", "right", "bye"]
        self.control_row = grid_size or self.logic.grid_size
        self.grid_size = grid_size or self.logic.grid_size

        self.client._2048_games.append(self)

        counter = 0

        for i in range(self.grid_size):
            for _ in range(self.grid_size):
                btn = ui.Button(
                    label=self.logic.blocks[counter].display,
                    row=i,
                    disabled=False if self.logic.blocks[counter].value > 0 else True,
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"2048-button-{counter}",
                )

                self.add_item(btn)

                counter += 1

        for i in range(5):
            attr = getattr(self, self.controls[i], None)
            if attr is not None:
                emoji: NewEmote = getattr(DirectionEmotes, self.controls[i].upper())
                style = discord.ButtonStyle.primary
                if self.controls[i] == "bye":
                    style = discord.ButtonStyle.danger

                item = ui.Button(emoji=emoji, style=style, row=self.control_row)
                item.callback = attr
                self.add_item(item)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} game={self.logic}>"

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if interaction.user.id != self.logic.player.id:
            await interaction.response.send_message(content=c(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for btn in self.children:
            if isinstance(btn, ui.Button):
                btn.disabled = True

                if btn.style == discord.ButtonStyle.success:
                    btn.style = discord.ButtonStyle.secondary

        channel = self.client.get_channel(self.interaction.channel.id)

        message = await channel.fetch_message(self.original_message.id)
        await message.edit(view=self)

        await self.original_message.reply(
            "\n".join(
                [
                    f"ok im guessing you just {BotEmojis.PEACE}'d out on me "
                    f"cuz you havent clicked anything for 2 minutes {self.logic.player.mention}",
                    "",
                    "(i saved your game btw, you can keep playing with `/2048`, setting `load` to true)",
                ]
            )
        )

        await self.async_stop(save=True)

    def update(self):
        self._children = sorted(self.children, key=lambda o: o.row)
        for block in self.logic.blocks:
            btn: ui.Button = self.children[block.list_index]
            btn.label = block.display
            btn.style = discord.ButtonStyle.secondary

            btn.disabled = False if block.value > 0 else True

            if block == self.logic.new_block:
                btn.style = discord.ButtonStyle.success
                btn.disabled = True

            if not self.logic._won:
                if (
                    block.value == 2048
                    and self.grid_size == 4
                    or block.value == 1024
                    and self.grid_size == 3
                    or block.value == 32
                    and self.grid_size == 2
                ):
                    self.logic._won = True

        return self.logic._won

    async def async_stop(self, save: bool = True):
        self.client._2048_games.remove(self)

        if save is True:
            query = """INSERT INTO twfe_games (user_id, blocks, score, moves)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT ON CONSTRAINT twfe_games_pkey
                        DO UPDATE SET
                            blocks = $2,
                            score = $3,
                            moves = $4
                        WHERE twfe_games.user_id = $1
                    """
            await self.client.db.execute(
                query,
                self.logic.player.id,
                [b.value for b in self.logic.blocks],
                self.logic.score,
                self.logic.moves,
            )
        else:
            query = """DELETE FROM twfe_games
                        WHERE user_id = $1
                    """
            await self.client.db.execute(query, self.logic.player.id)

        return super().stop()

    async def won(self, interaction: Interaction):
        await interaction.followup.send(f"Ggs you won ig")

    async def loss(self, interaction: Interaction):
        for btn in self.children:
            btn.disabled = True

            if btn.style == discord.ButtonStyle.success:
                btn.style = discord.ButtonStyle.secondary

        if not self.logic._won:
            await interaction.response.send_message(f"you lose. imagine losing.")

        else:
            await interaction.response.send_message(
                f"you lost but you still won :ok_hand:"
            )

        await interaction.followup.edit_message(
            message_id=self.original_message.id, view=self
        )

        return await self.async_stop(save=False)

    async def left(self, interaction: Interaction):
        try:
            already_won = self.logic._won
            self.logic.move(Directions.LEFT)
            loss = self.logic.check_loss(self.logic.blocks)
            won = self.update()

            self.embed.description = f"— **score** `{self.logic.score:,}`\n— **moves** `{self.logic.moves:,}`"

            if loss:
                return await self.loss(interaction)

            if won and not already_won:
                await interaction.response.edit_message(embed=self.embed, view=self)
                await self.won(interaction)
                return

            await interaction.response.edit_message(embed=self.embed, view=self)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def up(self, interaction: Interaction):
        try:
            already_won = self.logic._won
            self.logic.move(Directions.UP)
            loss = self.logic.check_loss(self.logic.blocks)
            won = self.update()

            self.embed.description = f"— **score** `{self.logic.score:,}`\n— **moves** `{self.logic.moves:,}`"

            if loss:
                return await self.loss(interaction)

            if won and not already_won:
                await interaction.response.edit_message(embed=self.embed, view=self)
                await self.won(interaction)
                return

            await interaction.response.edit_message(embed=self.embed, view=self)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def down(self, interaction: Interaction):
        try:
            already_won = self.logic._won
            self.logic.move(Directions.DOWN)
            loss = self.logic.check_loss(self.logic.blocks)
            won = self.update()

            self.embed.description = f"— **score** `{self.logic.score:,}`\n— **moves** `{self.logic.moves:,}`"

            if loss:
                return await self.loss(interaction)

            if won and not already_won:
                await interaction.response.edit_message(embed=self.embed, view=self)
                await self.won(interaction)
                return

            await interaction.response.edit_message(embed=self.embed, view=self)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def right(self, interaction: Interaction):
        try:
            already_won = self.logic._won
            self.logic.move(Directions.RIGHT)
            loss = self.logic.check_loss(self.logic.blocks)
            won = self.update()

            self.embed.description = f"— **score** `{self.logic.score:,}`\n— **moves** `{self.logic.moves:,}`"

            if loss:
                return await self.loss(interaction)

            if won and not already_won:
                await interaction.response.edit_message(embed=self.embed, view=self)
                await self.won(interaction)
                return

            await interaction.response.edit_message(embed=self.embed, view=self)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def bye(self, interaction: Interaction):
        try:
            for btn in self.children:
                btn.disabled = True

                if btn.style == discord.ButtonStyle.success:
                    btn.style = discord.ButtonStyle.secondary

            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "wanna save your game?", view=QuitConfirmationView(self), ephemeral=True
            )

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))


class QuitConfirmationView(ui.View):
    def __init__(self, game: Game):
        super().__init__(timeout=120)
        self.game = game

    async def on_timeout(self) -> None:
        return await self.game.async_stop()

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.game.logic.player.id:
            await interaction.response.send_message(content=c(CHOICES), ephemeral=True)
            return False
        return True

    @ui.select(
        placeholder="ye / nu",
        max_values=1,
        min_values=1,
        options=[
            discord.SelectOption(
                label="ye",
                description="keep playing later with /2048 and set load to true",
                emoji=NewEmote.from_name(BotEmojis.YES),
            ),
            discord.SelectOption(
                label="nu",
                description="trash out this current game",
                emoji=NewEmote.from_name(BotEmojis.NO),
            ),
        ],
    )
    async def select_callback(self, interaction: Interaction, select: ui.Select):
        bool_map = {"ye": True, "nu": False}
        await self.game.async_stop(save=bool_map[self.children[0].values[0]])
        self.stop()
        select.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("kbai", ephemeral=True)


class EditControlsView(ui.View):
    def __init__(
        self, interaction: Interaction, client: NotGDKID, controls: List[str | None]
    ) -> None:
        self.interaction = interaction
        self.client = client
        self.original_message: InteractionMessage = None
        self.changes = controls or ["left", "up", "down", "right", "bye"]
        self.original = self.changes.copy()
        self.editing = 0

        super().__init__(timeout=120)

        for i in range(5):
            btn: ui.Button = self.children[i]
            if hasattr(self.changes[i], "upper"):
                search = self.changes[i].upper()
            else:
                search = "ass"

            emoji = getattr(DirectionEmotes, search, None)
            if emoji is not None:
                btn.emoji = emoji
                btn.label = None

            else:
                btn.label = "none"

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message(content=c(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            c.disabled = True
            if isinstance(c, ui.Button):
                c.style = discord.ButtonStyle.secondary

        self.children[-1].style = discord.ButtonStyle.success

        try:
            msg = await self.original_message.channel.fetch_message(
                self.original_message.id
            )
            await msg.edit(view=self)

        except discord.NotFound:
            pass

        return await self.async_stop()

    async def async_stop(self) -> None:
        if self.changes != self.original:
            query = """INSERT INTO twfe_controls (
                            user_id,
                            {0}
                        ) VALUES ($6, $1, $2, $3, $4, $5)
                        ON CONFLICT ON CONSTRAINT twfe_controls_pkey
                        DO UPDATE SET 
                            {1}
                        WHERE twfe_controls.user_id = $6
                    """.format(
                ", ".join([f"slot_{i + 1}" for i in range(5)]),
                ", ".join([f"slot_{i + 1} = ${i + 1}" for i in range(5)]),
            )

            await self.client.db.execute(query, *self.changes, self.interaction.user.id)

        return super().stop()

    def generate_options(self):
        left = SelectOption(
            emoji=DirectionEmotes.LEFT, label="left", description="button to move left"
        )
        up = SelectOption(
            emoji=DirectionEmotes.UP, label="up", description="button to move up"
        )
        down = SelectOption(
            emoji=DirectionEmotes.DOWN, label="down", description="button to move down"
        )
        right = SelectOption(
            emoji=DirectionEmotes.RIGHT,
            label="right",
            description="button to move right",
        )
        bye = SelectOption(
            emoji=DirectionEmotes.BYE,
            label="bye",
            description="button to quit the game",
        )
        none = SelectOption(emoji=None, label="none", description="no button")

        return [
            o
            for o in [left, up, down, right, bye, none]
            if o.label != self.changes[self.editing]
        ]

    @ui.button(style=discord.ButtonStyle.secondary)
    async def slot_1(self, interaction: Interaction, button: ui.Button):
        for c in self.children:
            if isinstance(c, ui.Button):
                c.style = discord.ButtonStyle.secondary
                c.disabled = False

        for o in self.children[5].options:
            o.default = False

        button.disabled = True
        button.style = discord.ButtonStyle.success
        self.editing = 0
        self.children[5].disabled = False
        self.children[5].options = self.generate_options()

        return await interaction.response.edit_message(view=self)

    @ui.button(style=discord.ButtonStyle.secondary)
    async def slot_2(self, interaction: Interaction, button: ui.Button):
        for c in self.children:
            if isinstance(c, ui.Button):
                c.style = discord.ButtonStyle.secondary
                c.disabled = False

        for o in self.children[5].options:
            o.default = False

        button.disabled = True
        button.style = discord.ButtonStyle.success
        self.editing = 1
        self.children[5].disabled = False
        self.children[5].options = self.generate_options()

        return await interaction.response.edit_message(view=self)

    @ui.button(style=discord.ButtonStyle.secondary)
    async def slot_3(self, interaction: Interaction, button: ui.Button):
        for c in self.children:
            if isinstance(c, ui.Button):
                c.style = discord.ButtonStyle.secondary
                c.disabled = False

        for o in self.children[5].options:
            o.default = False

        button.disabled = True
        button.style = discord.ButtonStyle.success
        self.editing = 2
        self.children[5].disabled = False
        self.children[5].options = self.generate_options()

        return await interaction.response.edit_message(view=self)

    @ui.button(style=discord.ButtonStyle.secondary)
    async def slot_4(self, interaction: Interaction, button: ui.Button):
        for c in self.children:
            if isinstance(c, ui.Button):
                c.style = discord.ButtonStyle.secondary
                c.disabled = False

        for o in self.children[5].options:
            o.default = False

        button.disabled = True
        button.style = discord.ButtonStyle.success
        self.editing = 3
        self.children[5].disabled = False
        self.children[5].options = self.generate_options()

        return await interaction.response.edit_message(view=self)

    @ui.button(style=discord.ButtonStyle.secondary)
    async def slot_5(self, interaction: Interaction, button: ui.Button):
        for c in self.children:
            if isinstance(c, ui.Button):
                c.style = discord.ButtonStyle.secondary
                c.disabled = False

        for o in self.children[5].options:
            o.default = False

        button.disabled = True
        button.style = discord.ButtonStyle.success
        self.editing = 4
        self.children[5].disabled = False
        self.children[5].options = self.generate_options()

        return await interaction.response.edit_message(view=self)

    @ui.select(
        placeholder="pick an option...",
        disabled=True,
        max_values=1,
        min_values=1,
        options=[discord.SelectOption(label="\u200b")],
    )
    async def select(self, interaction: Interaction, select: ui.Select):
        if select.values[0] == "none":
            changed_to = None
        else:
            changed_to = select.values[0]

        self.changes[self.editing] = changed_to
        select.options = self.generate_options()

        for i in range(5):
            btn: ui.Button = self.children[i]
            if hasattr(self.changes[i], "upper"):
                search = self.changes[i].upper()
            else:
                search = "ass"

            emoji = getattr(DirectionEmotes, search, None)
            if emoji is not None:
                btn.emoji = emoji
                btn.label = None

            else:
                btn.label = "none"
                btn.emoji = None

        return await interaction.response.edit_message(view=self)

    @ui.button(label="save changes", style=discord.ButtonStyle.success, row=2)
    async def exit_menu(self, interaction: Interaction, btn: ui.Button):
        for c in self.children:
            c.disabled = True
            if isinstance(c, ui.Button):
                c.style = discord.ButtonStyle.secondary

        btn.style = discord.ButtonStyle.success

        await interaction.response.edit_message(view=self)
        await interaction.followup.send("done", ephemeral=True)
        return await self.async_stop()


class TwentyFortyEight(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("2048 cog loaded")

    @command(name="2048")
    @describe(grid_size="what size grid you want", load="load a previously saved game")
    @choices(
        grid_size=[
            Choice(name="4x4", value=4),
            Choice(name="3x3 (win at 1024)", value=3),
            Choice(name="2x2 (win at 32)", value=2),
        ]
    )
    async def twentyfortyeight(
        self,
        interaction: Interaction,
        grid_size: Optional[Choice[int]] = 4,
        load: Optional[bool] = False,
    ):
        """play 2048"""

        for game in self.client._2048_games:
            game: Game
            if game.logic.player.id == interaction.user.id:
                raise MaxConcurrencyReached(game.original_message.jump_url)

        if isinstance(grid_size, Choice):
            grid_size = grid_size.value

        infoEmbed = discord.Embed(
            description="— **score** `0`\n— **moves** `0`", colour=Botcolours.green
        )
        infoEmbed.set_footer(text="newly spawned blocks are highlighted in green")

        infoEmbed.set_author(
            name=f"{grid_size}x{grid_size} grid (win at {win_map[grid_size]} tile)",
            icon_url=interaction.client.user.avatar.url,
        )

        controls = []
        query = """SELECT (
                        slot_1,
                        slot_2,
                        slot_3,
                        slot_4,
                        slot_5
                    ) FROM twfe_controls WHERE user_id = $1
                """
        data = await self.client.db.fetchrow(query, interaction.user.id)
        if data:
            controls = [str(data[0][i]).lower() for i in range(5)]

        if load is True:
            query = """SELECT (blocks, score, moves) FROM twfe_games 
                        WHERE user_id = $1
                    """
            data = await self.client.db.fetchrow(query, interaction.user.id)
            if not data:
                return await interaction.response.send_message(
                    "couldnt find a saved game", ephemeral=True
                )
            blocks, score, moves = data[0]

            infoEmbed.description = f"— **score** `{score}`\n— **moves** `{moves}`"

            view = Game(
                interaction,
                blocks=blocks,
                score=score,
                moves=moves,
                embed=infoEmbed,
                controls=controls,
            )

        else:
            view = Game(interaction, grid_size, embed=infoEmbed, controls=controls)

        await interaction.response.send_message(embed=infoEmbed, view=view)
        setattr(view, "original_message", await interaction.original_message())

        await view.wait()

    twentyfortyeightconf = Group(name="2048conf", description="configuration commands")

    @twentyfortyeightconf.command(name="controls")
    @commands.max_concurrency(1, commands.BucketType.user)
    async def twentyfortyeight_config_controls(self, interaction: Interaction):
        """edit controls"""

        li = []
        query = """SELECT (
                        slot_1,
                        slot_2,
                        slot_3,
                        slot_4,
                        slot_5
                    ) FROM twfe_controls WHERE user_id = $1
                """
        data = await self.client.db.fetchrow(query, interaction.user.id)
        if data:
            li = [data[0][i] for i in range(5)]

        view = EditControlsView(interaction, self.client, li)

        await interaction.response.send_message(view=view)
        setattr(view, "original_message", await interaction.original_message())
        await view.wait()

    @twentyfortyeightconf.command(name="resetcontrols")
    async def twentyfortyeight_config_reset_controls(self, interaction: Interaction):
        """resets your control setup"""
        query = """DELETE FROM twfe_controls
                    WHERE user_id = $1 RETURNING user_id
                """
        data = await self.client.db.fetchrow(query, interaction.user.id)

        if data:
            msg = f"reset your control layout to default {BotEmojis.HEHEBOI}"

        else:
            msg = f"couldnt find your control layout {BotEmojis.HAHALOL}"

        await interaction.response.send_message(msg, ephemeral=True)

    @twentyfortyeightconf.command(name="deletesave")
    async def twentyfortyeight_delete_save(self, interaction: Interaction):
        """delete your saved game"""
        query = """DELETE FROM twfe_games
                    WHERE user_id = $1 RETURNING user_id
                """
        data = await self.client.db.fetchrow(query, interaction.user.id)

        if data:
            msg = f"found your save {BotEmojis.HEHEBOI} its gone now :)"

        else:
            msg = f"no save found {BotEmojis.HAHALOL}"

        await interaction.response.send_message(msg, ephemeral=True)

    @twentyfortyeight.error
    async def twentyfortyeight_error(self, interaction: Interaction, error):
        print(traceback.format_exc())
        if isinstance(error, MaxConcurrencyReached):
            author_game = error.jump_url

            return await interaction.response.send_message(
                "you already have a game going on" f"\n[jump to game](<{author_game}>)",
                ephemeral=True,
            )


async def setup(client: commands.Bot):
    await client.add_cog(TwentyFortyEight(client=client))
