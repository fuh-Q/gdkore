from __future__ import annotations

from datetime import datetime
from enum import Enum
import io
import time
from PIL import Image, ImageDraw
from typing import TYPE_CHECKING, Dict, List, Tuple, Optional

import discord
from discord import Interaction, InteractionMessage, ui
from discord.app_commands import command, describe, Range, CheckFailure, AppCommandError
from discord.ext import commands

from utils import Maze, GameView, Confirm, BlockTypes, BotEmojis, BotColours, humanize_timedelta, PrintColours

if TYPE_CHECKING:
    from bot import Amaze

class Directions(Enum):
    """
    Format
    ------
    MEMBER_NAME = (axis: str, positive_diff: bool, vertical: bool)
    """
    
    LEFT = ("x", False, False)
    UP = ("y", False, True)
    DOWN = ("y", True, True)
    RIGHT = ("x", True, False)


class MaxConcurrencyReached(CheckFailure):
    def __init__(self, jump_url: str) -> None:
        self.jump_url = jump_url


class MoveButton(ui.Button):
    @property
    def view(self) -> Game:
        return self._view

    def __init__(self, direction: Directions, modal_prompt: bool) -> None:
        row = int(modal_prompt)
        self.use_modal = modal_prompt
        self.direction = direction

        emoji = getattr(BotEmojis, f"MAZE_{direction.name}_{row + 1}")

        super().__init__(
            row=row,
            emoji=emoji,
        )

    async def callback(self, interaction: Interaction) -> None:
        axis, positive, vertical = self.direction.value
        if not self.use_modal:
            if vertical:
                block = self.view.maze._get_block(self.view.x, self.view.y + (1 if positive else -1))
                self.view.y += 2 if positive else -2
            else:
                block = self.view.maze._get_block(self.view.x + (1 if positive else -1), self.view.y)
                self.view.x += 2 if positive else -2
            
            if not block or block and block._block_type is BlockTypes.WALL:
                return
        else:
            return await interaction.response.send_modal(MoveModal(self.direction, self.view))
        
        await self.view.update_player(interaction, axis)


class MoveModal(ui.Modal):
    text = ui.TextInput(
        label="move spaces (\"max\" to go as far as possible)",
        placeholder="use \"max\" or leave blank to go as far as possible!",
        required=False,
        default="max",
        min_length=1,
        max_length=3,
    )
    
    def __init__(self, direction: Directions, game: Game) -> None:
        self.game = game
        self.direction = direction
        self.width = self.game.maze._width // 2 + 1
        self.height = self.game.maze._height // 2 + 1
        title = "move x spaces %s%s" % (
            "to the " if direction.value[0] == "x" else "",
            direction.name.lower()
        )
        
        super().__init__(
            title=title, timeout=None
        )
    
    async def on_submit(self, interaction: Interaction) -> None:
        axis, positive, vertical = self.direction.value
        try:
            value = int(self.text.value)
        except ValueError:
            if not self.text.value.lower() == "max":
                return await interaction.response.send_message(
                    "please enter a number of spaces to move or \"max\"",
                    ephemeral=True
                )
            value = None
        else:
            if (
                not vertical and value not in range(1, self.width + 1)
                or vertical and value not in range(1, self.height + 1)
            ):
                return await interaction.response.send_message(
                    f"you cant move that far {BotEmojis.HAHALOL}",
                    ephemeral=True
                )
        
        unit = self.game.maze._height if vertical else self.game.maze._width
        vu = unit if not value else value * 2
        r = range(1, vu + 1) if positive else range(-1, -vu - 1, -1)
        
        stop = 0
        for i in r:
            if vertical:
                block = self.game.maze._get_block(self.game.x, added := self.game.y + i)
            else:
                block = self.game.maze._get_block(added := self.game.x + i, self.game.y)
            
            if not block or block._block_type is BlockTypes.WALL:
                if stop:
                    added = getattr(self.game, axis) + (stop if positive else -stop)
                    break
                
                return await interaction.response.defer()
            
            if not i % 2:
                stop += 2
        
        await self.game.update_player(interaction, axis, added)


class Game(GameView):
    original_message: InteractionMessage
    
    def __init__(self):
        self.original_message = None
        
        super().__init__(timeout=180)
        
        og_children = self.children.copy()
        self.clear_items()
        
        for item in Directions:
            self.add_item(MoveButton(item, False))
            self.add_item(MoveButton(item, True))
        
        for item in og_children:
            self.add_item(item)
        
        self.fill_gaps()
    
    def setup(
        self,
        client: Amaze,
        settings_uid: int | None,
        path_rgb: Tuple[int] | None,
        wall_rgb: Tuple[int] | None,
        title: str | None,
        player_icon: bytes | None,
        finish_icon: bytes | None,
        mazes_uid: int | None,
        maze_blocks: List[Dict[str, int]] | None,
        width: int,
        height: int,
        start: datetime,
        moves: int,
        pos_x: int,
        pos_y: int,
    ):
        wall_rgb, path_rgb = map(lambda i: tuple(i) if i is not None else i, (wall_rgb, path_rgb))
        
        self.client = client
        self.owner_id = mazes_uid or settings_uid
        self.title = title
        self.started_at = start
        self.move_count = moves
        if not maze_blocks:
            self.maze = Maze(width, height)
        else:
            self.maze = Maze.from_db_columns(maze_blocks, width, height)
        
        maze_pic = self.maze.to_image(
            path_rgb or (190, 151, 111),
            wall_rgb or (0, 0, 0),
            finish_icon
        )
        del finish_icon
        
        size = (int(maze_pic.width * 1.1),
                int(maze_pic.height * 1.1))
        if title:
            fontsize = client.maze_font.getsize(title)
            img_width = fontsize[0] + 30
            img_height = fontsize[1] + 20
            
            size = (max((int(maze_pic.width * 1.1), img_width)),
                    int(maze_pic.height * 1.1) + img_height)
        else:
            fontsize = (0, 0)
        
        with Image.new(
            "RGBA",
            size,
            path_rgb or (190, 151, 111)
        ) as self.main_pic:
            if title:
                width = (self.main_pic.width - fontsize[0]) / 2
                ImageDraw.Draw(self.main_pic).text(
                    (width, 15),
                    title,
                    fill=wall_rgb or (0, 0, 0),
                    font=client.maze_font,
                )
            self.main_pic.paste(
                maze_pic,
                ((x := int((self.main_pic.width - maze_pic.width) / 2)),
                y := int((self.main_pic.height - maze_pic.height) / 2 + (10 if title else 0)))
            )
            maze_pic.close()
            del maze_pic
        
        if player_icon:
            self.player_icon = Image.open(io.BytesIO(player_icon))
            del player_icon
        else:
            bw = "black" if not path_rgb or path_rgb and sum(path_rgb) > 382 else "white"
            self.player_icon = Image.open(f"assets/default-player-{bw}.png")
            
        if self.player_icon.mode != "RGBA":
            self.player_icon = self.player_icon.convert("RGBA")
        
        self.x, self.y = pos_x, pos_y
        self.paste_x = x + 5
        self.paste_y = y + 5
    
    def maze_completed(self) -> bool:
        return self.x == self.maze._width - 1 and self.y == self.maze._height - 1
    
    def to_file(self) -> discord.File:
        buffer = io.BytesIO()
        copy = self.main_pic.copy()
        copy.paste(
            self.player_icon,
            (self.paste_x + self.x * 20, self.paste_y + self.y * 20),
            self.player_icon
        )
        copy.save(buffer, "png")
        buffer.seek(0)
        copy.close()
        del copy

        return discord.File(buffer, "maze.png")

    async def update_player(self, interaction: Interaction, axis: str, pos: int = None):
        self.move_count += 1
        if pos is not None:
            setattr(self, axis, pos)
        
        content = ""
        done = self.maze_completed()
        if done:
            taken = humanize_timedelta(seconds=time.time() - self.started_at.timestamp())
            await self.stop(save=False)
            self.disable_all()
            content = "**you finished!**\n\n" \
                     f"— **time taken** `{taken}`\n" \
                     f"— **moves** `{self.move_count}`\n\u200b"
        
        await interaction.response.edit_message(
            content=content,
            attachments=[await self.client.loop.run_in_executor(None, self.to_file)],
            view=None if done else self
        )
        
        if done:
            await self.client.loop.run_in_executor(None, self.ram_cleanup)
    
    async def stop(self, save: bool = False, shutdown_mode: bool = False) -> None:
        super().stop()
        
        if save or shutdown_mode:
            query = """INSERT INTO mazes VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT ON CONSTRAINT mazes_pkey
                        DO UPDATE SET
                            blocks = $2,
                            width = $3,
                            height = $4,
                            moves = $6,
                            pos_x = $7,
                            pos_y = $8
                        WHERE excluded.user_id = $1
                    """
            await self.client.db.execute(
                query,
                self.owner_id,
                [{"x": bl._x,
                "y": bl._y,
                "type": 1 if bl._block_type is BlockTypes.PATH else 0} for bl in self.maze._blocks],
                self.maze._width,
                self.maze._height,
                self.started_at,
                self.move_count,
                self.x,
                self.y,
            )
        
        else:
            query = """DELETE FROM mazes WHERE user_id = $1"""
            await self.client.db.execute(query, self.owner_id)
        
        if not shutdown_mode:
            del self.client._mazes[self.owner_id]
    
    def ram_cleanup(self):
        self.main_pic.close()
        self.player_icon.close()
        self.maze._ram_cleanup()
        del self.maze
        del self.main_pic
        del self.player_icon
        del self
    
    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("its not your game", ephemeral=True)
            return False
        
        if item.__class__.__name__ != "cls":
            return None

        return True
    
    async def on_timeout(self) -> None:
        self.disable_all()
        content = f"ok im guessing you just {BotEmojis.PEACE}'d out on me " \
                  f"since you havent clicked anything for {humanize_timedelta(seconds=self.timeout)} " \
                  f"<@!{self.owner_id}>\n\n" \
                  f"(i saved your game btw, you can keep playing the next time you run `/maze`)"
        await self.original_message.edit(content=content, view=self)
        
        await self.stop(save=True)
        await self.client.loop.run_in_executor(None, self.ram_cleanup)
    
    @ui.button(emoji=BotEmojis.QUIT_GAME, style=discord.ButtonStyle.danger)
    async def forfeit(self, interaction: Interaction, btn: ui.Button):
        view = Confirm(
            interaction.user,
            default=True,
            add_third=True,
            yes_label="save",
            no_label="dont save",
            third_label="cancel",
        )
        embed = discord.Embed(
            title="end game",
            description="would you like to save your game?",
            colour=BotColours.red,
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.original_message = await interaction.original_message()

        timeout = await view.wait()
        if timeout:
            view.disable_all()
            return await view.original_message.edit(view=view)

        await view.interaction.response.edit_message(view=view)
        if view.choice is None:
            return await view.interaction.followup.send("phew, dodged a bullet there", ephemeral=True)

        if not self.is_finished():
            self.disable_all()
            await self.stop(save=view.choice)
            
            if view.choice is False:
                content = f"<@!{self.owner_id}> gave up lol\n\u200b"
            else:
                content = f"<@!{self.owner_id}> alrighty, your game has been saved :)\n\u200b"
            
            await view.interaction.followup.edit_message(
                self.original_message.id,
                content=content,
                view=self
            )
            
            await self.client.loop.run_in_executor(None, self.ram_cleanup)


class Mazes(commands.Cog):
    def __init__(self, client: Amaze):
        self.client = client
    
    @staticmethod
    def _recal_width_and_height(width: int, height: int):
        return width * 2 - 1, height * 2 - 1
    
    @command(name="maze")
    @describe(
        width="the width of the maze (default 15)",
        height="the height of the maze (default 10)"
    )
    async def maze(self, interaction: Interaction, width: Optional[Range[int, 5, 25]] = 15, height: Optional[Range[int, 5, 25]] = 10):
        """
        generates a maze puzzle with the given width and height
        """
        
        if interaction.user.id in self.client._mazes:
            raise MaxConcurrencyReached(
                self.client._mazes[interaction.user.id].original_message.jump_url
            )
        
        width, height = self._recal_width_and_height(width, height)
        await interaction.response.send_message("building maze...")
        original_message = await interaction.original_message()
        
        async def new_game(args = None):
            if args is not None and args["started_at"]:
                query = """DELETE FROM mazes WHERE user_id = $1"""
                await self.client.db.execute(query, interaction.user.id)
                await view.interaction.response.edit_message(content="building maze...", embed=None, view=None)
            
            now = datetime.now()
            if args:
                settings = args[1:6]
            else:
                settings = (None for _ in range(5))
            zeroes = (0 for _ in range(3))
            game = Game()
            await self.client.loop.run_in_executor(
                None,
                game.setup,
                self.client, interaction.user.id, *settings, None, None, width, height, now, *zeroes
            )
            game.original_message = original_message
            self.client._mazes[interaction.user.id] = game
            
            await interaction.edit_original_message(
                content=None,
                attachments=[await self.client.loop.run_in_executor(None, game.to_file)],
                view=game
            )
            del args, game
        
        query = """SELECT *
                    FROM settings
                    FULL JOIN mazes
                    ON mazes.user_id = settings.user_id
                    WHERE mazes.user_id = $1 OR settings.user_id = $1
                """
        args = await self.client.db.fetchrow(query, interaction.user.id)
        if args is not None and args["started_at"]:
            embed = discord.Embed(
                title="save found",
                description="a previously saved game has been found, load save or overwrite?"
            )
            view = Confirm(interaction.user, yes_label="load", no_label="overwrite")
            await interaction.edit_original_message(content=None, embed=embed, view=view)
            view.original_message = original_message
            
            expired = await view.wait()
            if expired:
                for c in view.children:
                    c.disabled = True
                
                await interaction.edit_original_message(view=view)
                return
            
            if interaction.user.id in self.client._mazes:
                embed = discord.Embed(
                    description="you already have a game going on\n" \
                                f"[jump to game](<{self.client._mazes[interaction.user.id].original_message.jump_url}>)",
                    colour=BotColours.red
                )
                return await view.original_message.edit(embed=embed, view=None)
            
            if view.choice:
                game = Game()
                await self.client.loop.run_in_executor(
                    None,
                    game.setup,
                    self.client, *args
                )
                await view.interaction.response.edit_message(
                    embed=None,
                    attachments=[await self.client.loop.run_in_executor(None, game.to_file)],
                    view=game
                )
                
                game.original_message = original_message
                self.client._mazes[interaction.user.id] = game
                del args, game
                return
        
        await new_game(args)
    
    @maze.error
    async def maze_error(self, interaction: Interaction, error: AppCommandError):
        if isinstance(error, MaxConcurrencyReached):
            return await interaction.response.send_message(
                "you already have a game going on\n"
                f"[jump to game](<{error.jump_url}>)",
                ephemeral=True
            )


async def setup(client: Amaze):
    await client.add_cog(Mazes(client=client))
