import time
from enum import Enum
from random import choice as c
from random import choices as ch
from random import randint as r
from typing import Iterable, Optional

import discord
from discord.commands import (ApplicationContext, Option, OptionChoice,
                              slash_command)
from discord.ext import commands

from config.utils import CHOICES

weights = (90, 10)  # 2, 4


class Directions(Enum):
    LEFT = 1
    UP = 2
    DOWN = 3
    RIGHT = 4


class Game:
    def __init__(self, grid_size: int = 4):
        self.blocks: list[Block] = []
        self.grid_size = grid_size
        self.new_block = None
        self.player: discord.User = None

        self.moved: bool = False

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

    def check_loss(self, blocks: list["Block"]) -> bool:
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

    def _get_row(self, row: int, iterable: Optional[Iterable["Block"]] = None) -> list["Block"]:
        if not iterable:
            iterable = self.blocks

        o = []

        for b in iterable:
            if b.x == row:
                o.append(b)

        return o

    def _get_column(self, column: int, iterable: Optional[Iterable["Block"]] = None) -> list["Block"]:
        if not iterable:
            iterable = self.blocks

        o = []

        for b in iterable:
            if b.y == column:
                o.append(b)

        return o

    def _get_block(self, x, y, iterable: Optional[Iterable["Block"]] = None) -> Optional["Block"]:
        if not iterable:
            iterable = self.blocks

        for b in iterable:
            if b.x == x and b.y == y:
                return b

        return


class Block:
    def __init__(
        self,
        x: int,
        y: int,
        list_index: int,
        value: int = 0,
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
        return f"{self.value}"

    def __str__(self) -> str:
        return f"{self.value}"

    def swap(self, other: "Block"):
        x = self.x
        y = self.y
        list_index = self.list_index
        self.x = other.x
        self.y = other.y
        self.list_index = other.list_index
        other.x = x
        other.y = y
        other.list_index = list_index


class GameView(discord.ui.View):
    grid_size = 4

    def __init__(self, ctx: ApplicationContext, grid_size: int = 4):
        super().__init__(timeout=120)

        self.game = Game(grid_size=grid_size)
        self.game.player = ctx.user

        self.ctx = ctx
        self.message = None

        self.control_row = grid_size
        self.grid_size = grid_size

        self._hit_2048: bool = False

        counter = 0

        for i in range(grid_size):
            for _ in range(grid_size):
                btn = discord.ui.Button(
                    label=self.game.blocks[counter].display,
                    row=i,
                    disabled=False if self.game.blocks[counter].value > 0 else True,
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"2048-button-{counter}",
                )

                self.add_item(btn)

                counter += 1

    async def _scheduled_task(self, item: discord.ui.Item, interaction: discord.Interaction):
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.game.player.id:
            await interaction.response.send_message(content=c(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        del self.game
        for btn in self.children:
            if isinstance(btn, discord.ui.Button):
                btn.disabled = True
                btn.label = "\u200b"
                btn.style = discord.ButtonStyle.secondary

        await self.message.edit_original_message(view=self)

        msg: discord.InteractionMessage = await self.message.original_message()
        await msg.reply(
            f"ok im guessing you just <a:peace:951323779756326912>'d out on me cuz you havent clicked anything for 2 minutes"
        )

        self.stop()

    async def update(self):
        self.children = sorted(self.children, key=lambda o: o.row)
        for block in self.game.blocks:
            btn: discord.ui.Button = self.children[block.list_index]
            btn.label = block.display
            btn.style = discord.ButtonStyle.secondary

            btn.disabled = False if block.value > 0 else True
            
            if block == self.game.new_block:
                btn.style = discord.ButtonStyle.success
                btn.disabled = True

            if block.value == 2048 and not self._hit_2048:
                self._hit_2048 = True
                await self.hit_2048()

    async def hit_2048(self):
        msg = await self.message.original_message()
        await msg.reply("nice one")
    
    async def loss(self, interaction: discord.Interaction):
        for btn in self.children:
            btn.disabled = True
        
            if btn.style == discord.ButtonStyle.success:
                btn.style = discord.ButtonStyle.secondary

        await interaction.response.send_message("you lose. imagine losing.")
        await self.message.edit_original_message(view=self)
        return self.stop()

    @discord.ui.button(label="left", style=discord.ButtonStyle.primary, row=grid_size)
    async def left(self, _: discord.Button, interaction: discord.Interaction):
        self.game.move(Directions.LEFT)
        loss = self.game.check_loss(self.game.blocks)
        await self.update()
        if loss:
            await self.loss(interaction)

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="up", style=discord.ButtonStyle.primary, row=grid_size)
    async def up(self, _: discord.Button, interaction: discord.Interaction):
        self.game.move(Directions.UP)
        loss = self.game.check_loss(self.game.blocks)
        await self.update()
        if loss:
            await self.loss(interaction)

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="down", style=discord.ButtonStyle.primary, row=grid_size)
    async def down(self, _: discord.Button, interaction: discord.Interaction):
        self.game.move(Directions.DOWN)
        loss = self.game.check_loss(self.game.blocks)
        await self.update()
        if loss:
            await self.loss(interaction)

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="right", style=discord.ButtonStyle.primary, row=grid_size)
    async def right(self, _: discord.Button, interaction: discord.Interaction):
        self.game.move(Directions.RIGHT)
        loss = self.game.check_loss(self.game.blocks)
        await self.update()
        if loss:
            await self.loss(interaction)

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="bye", style=discord.ButtonStyle.danger, row=grid_size)
    async def end(self, _: discord.Button, interaction: discord.Interaction):
        del self.game
        for btn in self.children:
            btn.disabled = True
            btn.label = "\u200b"
            btn.style = discord.ButtonStyle.secondary

        await self.message.edit_original_message(view=self)
        await interaction.response.send_message("kbai", ephemeral=True)
        self.stop()


class TwentyFortyEight(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("2048 cog loaded")

    @slash_command(name="2048", guild_ids=[749892811905564672])
    async def twentyfortyeight(
        self,
        ctx: ApplicationContext,
        grid_size: Option(
            int,
            "what size grid you want",
            choices=[
                OptionChoice(name="4x4 (normal)", value=4),
                OptionChoice(name="3x3 (for super sweaty 2048 nerds)", value=3),
                OptionChoice(name="2x2 (literally impossible lmao)", value=2),
            ],
        ) = 4,
    ):
        """play 2048"""

        view = GameView(ctx, grid_size)

        msg = await ctx.respond("(newly spawned blocks are highlighted in green)", view=view)
        setattr(view, "message", msg)


def setup(client: commands.Bot):
    client.add_cog(TwentyFortyEight(client=client))
