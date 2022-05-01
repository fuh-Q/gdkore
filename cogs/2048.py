import math
import time
import traceback
from datetime import datetime
from enum import Enum
from random import choice as c
from random import choices as ch
from random import randint as r
from typing import Iterable, List, Optional

import discord
from discord import Interaction, InteractionMessage, SelectOption
from discord.app_commands import (CheckFailure, Choice, Group, choices,
                                  command, describe)
from discord.ext import commands

from bot import NotGDKID
from config.utils import CHOICES, Botcolours, NewEmote

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
    LEFT = NewEmote.from_name("<a:arrowleft:951720658256134144>")
    UP = NewEmote.from_name("<a:arrowup:951720658440708097>")
    DOWN = NewEmote.from_name("<a:arrowdown:951720657509564417>")
    RIGHT = NewEmote.from_name("<a:arrowright:951720658365186058>")
    BYE = NewEmote.from_name("<:bye:954097284482736128>")


class MaxConcurrencyReached(CheckFailure):
    ...


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


class Game:
    def __init__(self, grid_size: Optional[int] = 4, blocks: Optional[List[Block]] = None):
        self.blocks: List[Block] = blocks or []
        self.grid_size = grid_size
        self.new_block = None
        self.player: discord.User = None

        self.moved: bool = False
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
    def from_values(cls, blocks: List[int]):
        new_blocks: List[Block] = []

        counter = 0
        grid_size = round(math.sqrt(len(blocks)))

        for y in range(grid_size):
            for x in range(grid_size):
                new_blocks.append(Block(x, y, counter, blocks[counter]))
                counter += 1

        return cls(grid_size, new_blocks)

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
                self.moved = True
                break

    def check_loss(self, blocks: List[Block]) -> bool:
        if self.moved:
            empty_spaces = []
            for block in blocks:
                if block.value == 0:
                    empty_spaces.append(block)

            new: Block = c(empty_spaces)
            new_block = blocks[blocks.index(new)]
            new_block.value = ch([2, 4], weights=weights, k=1)[0]
            new_block.display = new_block.value
            self.new_block = new_block

        self.moved = False
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

    def _get_row(self, row: int, iterable: Optional[Iterable[Block]] = None) -> List[Block]:
        if not iterable:
            iterable = self.blocks

        o = []

        for b in iterable:
            if b.x == row:
                o.append(b)

        return o

    def _get_column(self, column: int, iterable: Optional[Iterable[Block]] = None) -> List[Block]:
        if not iterable:
            iterable = self.blocks

        o = []

        for b in iterable:
            if b.y == column:
                o.append(b)

        return o

    def _get_block(self, x, y, iterable: Optional[Iterable[Block]] = None) -> Optional[Block]:
        if not iterable:
            iterable = self.blocks

        for b in iterable:
            if b.x == x and b.y == y:
                return b

        return


class GameView(discord.ui.View):
    grid_size = 4

    def __init__(
        self,
        interaction: Interaction,
        grid_size: Optional[int] = None,
        blocks: Optional[List[int]] = None,
        client: Optional[NotGDKID] = None,
    ):
        super().__init__(timeout=120)

        self.game = Game.from_values(blocks) if blocks is not None and grid_size is None else Game(grid_size=grid_size)

        setattr(self.game, "player", interaction.user)

        self.interaction = interaction
        self.client: NotGDKID = client or interaction.client

        self.original_message: Optional[InteractionMessage] = None

        self.controls: List[str] = []
        self.control_row = grid_size or self.game.grid_size
        self.grid_size = grid_size or self.game.grid_size

        self.client._2048_games.append(self)

        for game in self.client.cache["2048games"]:
            if game["player"] == self.game.player.id:
                self.client.cache["2048games"].pop(self.client.cache["2048games"].index(game))

        self.client.cache["2048games"].append(
            {"player": self.game.player.id, "blocks": [b.value for b in self.game.blocks]}
        )

        counter = 0

        for i in range(self.grid_size):
            for _ in range(self.grid_size):
                btn = discord.ui.Button(
                    label=self.game.blocks[counter].display,
                    row=i,
                    disabled=False if self.game.blocks[counter].value > 0 else True,
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"2048-button-{counter}",
                )

                self.add_item(btn)

                counter += 1

        for setup in self.client.cache["controls"]:
            if setup["user"] == self.interaction.user.id:
                self.controls = setup["setup"]

        if len(self.controls) == 0:
            self.controls = ["left", "up", "down", "right", "bye"]

        for i in range(5):
            attr = getattr(self, self.controls[i], None)
            if attr is not None:
                emoji: NewEmote = getattr(DirectionEmotes, self.controls[i].upper())
                style = discord.ButtonStyle.primary
                if self.controls[i] == "bye":
                    style = discord.ButtonStyle.danger

                item = discord.ui.Button(emoji=emoji, style=style, row=self.control_row)
                item.callback = attr
                self.add_item(item)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} game={self.game}>"

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

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.game.player.id:
            await interaction.response.send_message(content=c(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for btn in self.children:
            if isinstance(btn, discord.ui.Button):
                btn.disabled = True

                if btn.style == discord.ButtonStyle.success:
                    btn.style = discord.ButtonStyle.secondary

        channel = self.client.get_channel(self.interaction.channel.id)

        message = await channel.fetch_message(self.original_message.id)
        await message.edit(view=self)

        await self.original_message.reply(
            "\n".join(
                [
                    "ok im guessing you just <a:peace:951323779756326912>'d out on me "
                    f"cuz you havent clicked anything for 2 minutes {self.game.player.mention}",
                    "",
                    "(i saved your game btw, you can keep playing with `/2048`, setting `load` to true)",
                ]
            )
        )

        self.stop(save=True)

    def update(self):
        self._children = sorted(self.children, key=lambda o: o.row)
        for block in self.game.blocks:
            btn: discord.ui.Button = self.children[block.list_index]
            btn.label = block.display
            btn.style = discord.ButtonStyle.secondary

            btn.disabled = False if block.value > 0 else True

            if block == self.game.new_block:
                btn.style = discord.ButtonStyle.success
                btn.disabled = True

            if not self.game._won:
                if (
                    block.value == 2048
                    and self.grid_size == 4
                    or block.value == 1024
                    and self.grid_size == 3
                    or block.value == 32
                    and self.grid_size == 2
                ):
                    self.game._won = True

        return self.game._won

    def stop(self, save: bool = True):
        self.client._2048_games.pop(self.client._2048_games.index(self))

        index = 0
        for game in self.client.cache["2048games"]:
            if game["player"] == self.game.player.id:
                if save is not True:
                    self.client.cache["2048games"].pop(self.client.cache["2048games"].index(game))
                    continue

                else:
                    self.client.cache["2048games"][index] = {
                        "player": self.game.player.id,
                        "blocks": [b.value for b in self.game.blocks],
                    }
                    break

            index += 1

        return super().stop()

    async def won(self, interaction: Interaction):
        await interaction.followup.send(f"Ggs you won ig")

    async def loss(self, interaction: Interaction):
        for btn in self.children:
            btn.disabled = True

            if btn.style == discord.ButtonStyle.success:
                btn.style = discord.ButtonStyle.secondary

        if not self.game._won:
            await interaction.response.send_message(f"you lose. imagine losing.")

        else:
            await interaction.response.send_message(f"you lost but you still won :ok_hand:")

        await interaction.followup.edit_message(message_id=self.original_message.id, view=self)

        return self.stop(save=False)

    async def left(self, interaction: Interaction):
        try:
            already_won = self.game._won
            self.game.move(Directions.LEFT)
            loss = self.game.check_loss(self.game.blocks)
            won = self.update()

            if loss:
                return await self.loss(interaction)

            if won and not already_won:
                await interaction.response.edit_message(view=self)
                await self.won(interaction)

            await interaction.response.edit_message(view=self)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def up(self, interaction: Interaction):
        try:
            already_won = self.game._won
            self.game.move(Directions.UP)
            loss = self.game.check_loss(self.game.blocks)
            won = self.update()

            if loss:
                return await self.loss(interaction)

            if won and not already_won:
                await interaction.response.edit_message(view=self)
                await self.won(interaction)

            await interaction.response.edit_message(view=self)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def down(self, interaction: Interaction):
        try:
            already_won = self.game._won
            self.game.move(Directions.DOWN)
            loss = self.game.check_loss(self.game.blocks)
            won = self.update()

            if loss:
                return await self.loss(interaction)

            if won and not already_won:
                await interaction.response.edit_message(view=self)
                await self.won(interaction)

            await interaction.response.edit_message(view=self)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def right(self, interaction: Interaction):
        try:
            already_won = self.game._won
            self.game.move(Directions.RIGHT)
            loss = self.game.check_loss(self.game.blocks)
            won = self.update()

            if loss:
                return await self.loss(interaction)

            if won and not already_won:
                await interaction.response.edit_message(view=self)
                await self.won(interaction)

            await interaction.response.edit_message(view=self)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))

    async def bye(self, interaction: Interaction):
        try:
            for btn in self.children:
                btn.disabled = True

                if btn.style == discord.ButtonStyle.success:
                    btn.style = discord.ButtonStyle.secondary

            await interaction.response.edit_message(view=self)
            await interaction.followup.send("wanna save your game?", view=QuitConfirmationView(self), ephemeral=True)

        except Exception as e:
            print("".join(traceback.format_exception(e, e, e.__traceback__)))


class QuitConfirmationView(discord.ui.View):
    def __init__(self, game: "GameView"):
        super().__init__(timeout=120)
        self.game = game

    async def on_timeout(self) -> None:
        return self.game.stop()

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.game.game.player.id:
            await interaction.response.send_message(content=c(CHOICES), ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="ye / nu",
        max_values=1,
        min_values=1,
        options=[
            discord.SelectOption(
                label="ye",
                description="keep playing later with /2048 and set load to true",
                emoji=NewEmote.from_name(NotGDKID.yes),
            ),
            discord.SelectOption(
                label="nu",
                description="trash out this current game",
                emoji=NewEmote.from_name(NotGDKID.no),
            ),
        ],
    )
    async def select_callback(self, interaction: Interaction, select: discord.ui.Select):
        bool_map = {"ye": True, "nu": False}
        self.game.stop(save=bool_map[self.children[0].values[0]])
        self.stop()
        select.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("kbai", ephemeral=True)


class EditControlsView(discord.ui.View):
    def __init__(self, interaction: Interaction, client: NotGDKID) -> None:
        self.interaction = interaction
        self.client = client
        self.original_message: InteractionMessage = None
        self.changes = []
        self.editing = 0

        for setup in self.client.cache["controls"]:
            if setup["user"] == self.interaction.user.id:
                self.changes = setup["setup"]

        if len(self.changes) == 0:
            self.changes = ["left", "up", "down", "right", "bye"]

        super().__init__(timeout=120)

        for i in range(5):
            btn: discord.ui.Button = self.children[i]

            emoji = getattr(DirectionEmotes, self.changes[i].upper(), None)
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
            if isinstance(c, discord.ui.Button):
                c.style = discord.ButtonStyle.secondary

        self.children[-1].style = discord.ButtonStyle.success

        try:
            msg = await self.original_message.channel.fetch_message(self.original_message.id)
            await msg.edit(view=self)

        except discord.NotFound:
            pass

        return self.stop()

    def stop(self) -> None:
        _set = False
        for setup in self.client.cache["controls"]:
            if setup["user"] == self.interaction.user.id:
                setup["setup"] = self.changes
                _set = True

        if not _set:
            self.client.cache["controls"].append({"user": self.interaction.user.id, "setup": self.changes})

        return super().stop()

    def generate_options(self):
        left = SelectOption(emoji=DirectionEmotes.LEFT, label="left", description="button to move left")
        up = SelectOption(emoji=DirectionEmotes.UP, label="up", description="button to move up")
        down = SelectOption(emoji=DirectionEmotes.DOWN, label="down", description="button to move down")
        right = SelectOption(emoji=DirectionEmotes.RIGHT, label="right", description="button to move right")
        bye = SelectOption(emoji=DirectionEmotes.BYE, label="bye", description="button to quit the game")
        none = SelectOption(emoji=None, label="none", description="no button")

        return [o for o in [left, up, down, right, bye, none] if o.label != self.changes[self.editing]]

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def slot_1(self, interaction: Interaction, button: discord.ui.Button):
        for c in self.children:
            if isinstance(c, discord.ui.Button):
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

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def slot_2(self, interaction: Interaction, button: discord.ui.Button):
        for c in self.children:
            if isinstance(c, discord.ui.Button):
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

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def slot_3(self, interaction: Interaction, button: discord.ui.Button):
        for c in self.children:
            if isinstance(c, discord.ui.Button):
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

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def slot_4(self, interaction: Interaction, button: discord.ui.Button):
        for c in self.children:
            if isinstance(c, discord.ui.Button):
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

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def slot_5(self, interaction: Interaction, button: discord.ui.Button):
        for c in self.children:
            if isinstance(c, discord.ui.Button):
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

    @discord.ui.select(
        placeholder="pick an option...",
        disabled=True,
        max_values=1,
        min_values=1,
        options=[discord.SelectOption(label="\u200b")],
    )
    async def select(self, interaction: Interaction, select: discord.ui.Select):
        changed_to = select.values[0]
        self.changes[self.editing] = changed_to
        select.options = self.generate_options()

        for i in range(5):
            btn: discord.ui.Button = self.children[i]

            emoji = getattr(DirectionEmotes, self.changes[i].upper(), None)
            if emoji is not None:
                btn.emoji = emoji
                btn.label = None

            else:
                btn.label = "none"
                btn.emoji = None

        return await interaction.response.edit_message(view=self)

    @discord.ui.button(label="save changes", style=discord.ButtonStyle.success, row=2)
    async def exit_menu(self, interaction: Interaction, btn: discord.ui.Button):
        for c in self.children:
            c.disabled = True
            if isinstance(c, discord.ui.Button):
                c.style = discord.ButtonStyle.secondary

        btn.style = discord.ButtonStyle.success

        await interaction.response.edit_message(view=self)
        await interaction.followup.send("done", ephemeral=True)
        return self.stop()


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
        self, interaction: Interaction, grid_size: Optional[Choice[int]] = 4, load: Optional[bool] = False
    ):
        """play 2048"""

        for game in self.client._2048_games:
            game: GameView
            if game.game.player.id == interaction.user.id:
                raise MaxConcurrencyReached

        if isinstance(grid_size, Choice):
            grid_size = grid_size.value

        if load is True:
            found = False

            for game in self.client.cache["2048games"]:
                if game["player"] == interaction.user.id:
                    found = True
                    grid_size = round(math.sqrt(len(game["blocks"])))
                    view = GameView(interaction, blocks=game["blocks"])
                    break

            if not found:
                return await interaction.response.send_message("couldnt find a saved game", ephemeral=True)

        else:
            view = GameView(interaction, grid_size)

        infoEmbed = discord.Embed(description="newly spawned blocks are highlighted in green", colour=Botcolours.green)

        infoEmbed.set_author(
            name=f"{grid_size}x{grid_size} grid (win at {win_map[grid_size]})",
            icon_url=interaction.client.user.avatar.url,
        )

        await interaction.response.send_message(embed=infoEmbed, view=view)
        setattr(view, "original_message", await interaction.original_message())

        await view.wait()

    twentyfortyeightconf = Group(name="2048conf", description="configuration commands")

    howto = Group(name="howto", description="2048 game guide")

    @howto.command(name="basic")
    async def howtobasic(self, interaction: Interaction):
        """2048 game guide"""

        avatars = [
            self.client.get_user(596481615253733408).avatar.url,
            self.client.get_user(865596669999054910).avatar.url,
            self.client.get_user(859104775429947432).avatar.url,
        ]

        info_embed = (
            discord.Embed(
                description="""
            **▫️ How to Play 2048**
            
            Click the controls {0} {1} {2} {3} to move the tiles around
            Each move will shift **all tiles** in that direction (wherever possible).
            
            When two tiles of the same value move into each other,
            they merge into one and their values are added together.
            
            Your job is to get to the **2048** {4} tile (if you're playing a 4x4 grid)
            *The winning tile on a 3x3 grid is **1024*** {5},
            *and **32** {6} if you're playing on a 2x2 grid*
            
            Each move spawns in a new tile to the board, highlighted 
            in green {7} for visibility. Once your board fills up with no more 
            possible moves, **you *__lose__. {8}***
            """.format(
                    str(DirectionEmotes.LEFT),
                    str(DirectionEmotes.UP),
                    str(DirectionEmotes.DOWN),
                    str(DirectionEmotes.RIGHT),
                    "<:2048:960746063285878795>",
                    "<:1024:960746063537528852>",
                    "<:32:960746063571075112>",
                    "🟩",
                    "💀",
                ),
                colour=Botcolours.yellow,
                timestamp=datetime.now(),
            )
            .set_author(
                name=interaction.client.user.name,
                url="https://levelskip.com/puzzle/How-to-play-2048",
                icon_url=c(avatars),
            )
            .set_thumbnail(url="https://www.gamebrew.org/images/6/64/2048_Screenshot.png")
            .set_footer(text="\u200b", icon_url=c(avatars))
        )

        return await interaction.response.send_message(embed=info_embed, ephemeral=True)

    @twentyfortyeightconf.command(name="controls")
    @commands.max_concurrency(1, commands.BucketType.user)
    async def twentyfortyeight_config_controls(self, interaction: Interaction):
        """edit controls"""

        view = EditControlsView(interaction, self.client)

        await interaction.response.send_message(view=view)
        setattr(view, "original_message", await interaction.original_message())
        await view.wait()

    @twentyfortyeightconf.command(name="resetcontrols")
    async def twentyfortyeight_config_reset_controls(self, interaction: Interaction):
        """resets your control setup"""

        found = False

        for setup in self.client.cache["controls"]:
            if setup["user"] == interaction.user.id:
                self.client.cache["controls"].pop(self.client.cache["controls"].index(setup))
                found = True

        if found:
            msg = "reset your control layout to default <:heheboi:953811490304061440>"

        else:
            msg = "couldnt find your control layout <a:hahalol:953811854201868340>"

        await interaction.response.send_message(msg, ephemeral=True)

    @twentyfortyeightconf.command(name="deletesave")
    async def twentyfortyeight_delete_save(self, interaction: Interaction):
        """delete your saved game"""
        found = False

        for game in self.client.cache["2048games"]:
            if game["player"] == interaction.user.id:
                self.client.cache["2048games"].pop(self.client.cache["2048games"].index(game))
                found = True

        if found:
            msg = "found your save <:heheboi:953811490304061440> its gone now :)"

        else:
            msg = "no save found <a:hahalol:953811854201868340>"

        await interaction.response.send_message(msg, ephemeral=True)

    @twentyfortyeight.error
    async def twentyfortyeight_error(self, interaction: Interaction, error):
        if isinstance(error, MaxConcurrencyReached):
            author_game = None

            for gameview in self.client._2048_games:
                gameview: GameView

                if gameview.game.player.id == interaction.user.id:
                    author_game = gameview.original_message.jump_url

            return await interaction.response.send_message(
                "you already have a game going on"
                f"\n{'[jump to game message](<' + author_game + '>)' if author_game is not None else ''}",
                ephemeral=True,
            )


async def setup(client: commands.Bot):
    await client.add_cog(TwentyFortyEight(client=client))
