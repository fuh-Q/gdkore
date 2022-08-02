from __future__ import annotations

from datetime import datetime
from enum import Enum
import io
import time
from PIL import Image, ImageDraw
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Optional, TypedDict
import asyncpg

import discord
from discord import Interaction, InteractionMessage, ui
from discord.ext import commands
from discord.app_commands import (
    errors,
    checks,
    command,
    choices,
    describe,
    Range,
    Choice,
    CheckFailure,
    AppCommandError
)

from utils import Maze, View, Confirm, BlockTypes, BotEmojis, BotColours, humanize_timedelta

if TYPE_CHECKING:
    from bot import Amaze

class Directions(Enum):
    """
    MEMBER_NAME = (axis: str, positive_diff: bool, vertical: bool)
    """
    
    LEFT = ("x", False, False)
    UP = ("y", False, True)
    DOWN = ("y", True, True)
    RIGHT = ("x", True, False)


class StopModes(Enum):
    """
    MEMBER_NAME = int
    """
    
    DELETE = 0
    SAVE = 1
    SHUTDOWN = 2
    COMPLETED = 3


class LeaderboardEntry(TypedDict):
    user_id: int
    best: float
    total: float
    average: float
    num_completed: int
    rank: int | None


class MazeGameEntry(TypedDict):
    user_id: int
    blocks: Dict[str, int]
    width: int
    height: int
    started_at: datetime
    moves: int
    pos_x: int
    pos_y: int
    path_rgb: List[int]
    wall_rgb: List[int]
    title: str
    player_icon: bytes
    finish_icon: bytes


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
                added = self.view.y + (2 if positive else -2)
            else:
                block = self.view.maze._get_block(self.view.x + (1 if positive else -1), self.view.y)
                added = self.view.x + (2 if positive else -2)
            
            if not block or block and block._block_type is BlockTypes.WALL:
                return
        else:
            return await interaction.response.send_modal(MoveModal(self.direction, self.view))
        
        await self.view.update_player(interaction, axis, added)


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


class Game(View):
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
        ranked: bool,
    ):
        wall_rgb, path_rgb = map(lambda i: tuple(i) if i is not None else i, (wall_rgb, path_rgb))
        if title is None:
            title = "please help mee6 to the trash"
        
        self.client = client
        self.owner_id = mazes_uid or settings_uid
        self.title = title
        self.started_at = start
        self.move_count = moves
        self.ranked = ranked
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
        
        size = (maze_pic.width + 50,
                maze_pic.height + 30)
        if title:
            fontsize = client.maze_font.getsize(title)
            img_width = fontsize[0] + 30
            img_height = fontsize[1] + 20
            
            size = (max(size[0], img_width),
                    size[1] + img_height)
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
                 y := int((self.main_pic.height - maze_pic.height) / 2) if not title else 61)
            )
            maze_pic.close()
            del maze_pic
        
        if player_icon:
            self.player_icon = Image.open(io.BytesIO(player_icon))
            del player_icon
        else:
            #bw = "black" if not path_rgb or path_rgb and sum(path_rgb) > 382 else "white"
            #self.player_icon = Image.open(f"assets/default-player-{bw}.png")
            self.player_icon = Image.open(f"assets/mee6.png")
            
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

    async def update_player(self, interaction: Interaction, axis: str, pos: int):
        self.move_count += 1
        setattr(self, axis, pos)
        
        content = ""
        done = self.maze_completed()
        if done:
            taken = humanize_timedelta(seconds=(seconds := time.time() - self.started_at.timestamp()))
            if self.ranked:
                score = round(
                    (self.maze._width * self.maze._height) ** 1.1 / (seconds + self.move_count) / 2.5, 2
                )
                bottom = "use `/leaderboard` to view your rank!"
            else:
                score = "NA"
                bottom = "score is not counted because you loaded a save"
            
            self.disable_all()
            content = "**you finished!**\n\n" \
                     f"— moves `{self.move_count}`\n" \
                     f"— total time `{taken}`\n\n" \
                     f"— **score** `{score}`\n" \
                     f"ㅤ*{bottom}*\n\u200b"
        
        await interaction.response.edit_message(
            content=content,
            attachments=[await self.client.loop.run_in_executor(None, self.to_file)],
            view=None if done else self
        )
        
        if done:
            await self.stop(mode=StopModes.COMPLETED)
            if self.ranked:
                await self.update_leaderboards(points=score)
            
            await self.client.loop.run_in_executor(None, self.ram_cleanup)
    
    async def update_leaderboards(self, points: float) -> None:
        q = """INSERT INTO leaderboards VALUES ($1, $2, $2, $2, 1)
                ON CONFLICT ON CONSTRAINT leaderboards_pkey
                DO UPDATE SET
                    best = CASE WHEN leaderboards.best > $2 THEN leaderboards.best ELSE $2 END,
                    total = leaderboards.total + $2,
                    average = (leaderboards.total + $2) / (leaderboards.num_completed + 1),
                    num_completed = leaderboards.num_completed + 1
                WHERE leaderboards.user_id = $1
            """
        
        await self.client.db.execute(q, self.owner_id, points)
    
    async def stop(self, mode: StopModes, *, shutdown: bool = False) -> None:
        super().stop()
        
        if mode not in (StopModes.DELETE, StopModes.COMPLETED):
            q = """INSERT INTO mazes VALUES ($1, $2, $3, $4, $5, $6, $7, $8, {0})
                    ON CONFLICT ON CONSTRAINT mazes_pkey
                    DO UPDATE SET
                        blocks = $2,
                        width = $3,
                        height = $4,
                        moves = $6,
                        pos_x = $7,
                        pos_y = $8,
                        keep_ranked = {0}
                    WHERE excluded.user_id = $1
                """.format("TRUE" if shutdown and self.ranked else "FALSE")
            await self.client.db.execute(
                q,
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
            q = """DELETE FROM mazes WHERE user_id = $1"""
            await self.client.db.execute(q, self.owner_id)
        
        if not shutdown:
            del self.client._mazes[self.owner_id]
    
    def ram_cleanup(self):
        self.main_pic.close()
        self.player_icon.close()
        self.maze._ram_cleanup()
        del (self.main_pic,
             self.player_icon,
             self.maze,
             self)
    
    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "its not your game, you can start one by running `/maze`", ephemeral=True
            )
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
        
        await self.stop(mode=StopModes.SAVE)
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
            title="quit game",
            description="would you like to save your game?\n\n"
                        "— **points will no longer be counted if you save**\n"
                        "— **giving up will score a `0` and will be counted on your average**",
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
            await self.stop(mode=list(StopModes.__members__.values())[int(view.choice)])
            
            if view.choice is False:
                content = f"<@!{self.owner_id}> gave up lol\n\u200b"
                await self.update_leaderboards(points=0.0)
            else:
                content = f"<@!{self.owner_id}> alrighty, your game has been saved :)\n\u200b"
            
            await view.interaction.followup.edit_message(
                self.original_message.id,
                content=content,
                view=self
            )
            
            await self.client.loop.run_in_executor(None, self.ram_cleanup)


class Leaderboards(View):
    original_message: InteractionMessage
    options = [
        discord.SelectOption(label="best score", value="best"),
        discord.SelectOption(label="average score", value="average"),
        discord.SelectOption(label="total score", value="total"),
    ]
    
    def __init__(self, client: Amaze, owner_id: int, cache: Dict[str, str]):
        self.client = client
        self.owner_id = owner_id
        self.cache = cache
        
        super().__init__(timeout=30)
        
        self.selected = list(cache)[0]
        self.select_menu.options = self.refresh_options()
    
    @staticmethod
    async def fetch_rankings(db: asyncpg.Pool | asyncpg.Connection, leaderboard: str, user_id: int) -> str:
        q = """SELECT * FROM leaderboards
                ORDER BY {0} DESC
                LIMIT 10
            """.format(leaderboard)
        top_10: List[LeaderboardEntry] = await db.fetch(q)
        
        rankings = "\n".join(map(lambda tu: f"`{tu[0] + 1:,}.` <@!{tu[1]['user_id']}> - `{tu[1][leaderboard]:,.2f}` points", enumerate(top_10)))
        
        if user_id not in map(lambda i: i["user_id"], top_10):
            q = """SELECT *, (
                        SELECT COUNT(*)
                        FROM leaderboards lb2
                        WHERE lb2.{0} >= lb.{0}
                    ) AS rank
                    FROM leaderboards lb
                    WHERE user_id = $1
                """.format(leaderboard)
            user: LeaderboardEntry = await db.fetchrow(q, user_id)
            if user:
                user_rank = f"\n`{user['rank']:,}.` <@!{user['user_id']}> - `{user[leaderboard]:,.2f}` points"
                if user["rank"] != 11:
                    user_rank = "\n..." + user_rank
            else:
                user_rank = f"\n...\n`NA.` <@!{user_id}> - `0` points"
            
            rankings += user_rank
        
        return rankings
    
    async def interaction_check(self, interaction: Interaction, item: ui.Button | ui.Select) -> bool:
        if item is self.formula:
            return None
        
        if item is self.select_menu and interaction.user.id != self.owner_id:
            embed = await self.get_embed(interaction, ranking=item.values[0], cache={self.selected: ""})
            
            view = Leaderboards(self.client, interaction.user.id, {self.selected: embed.description})
            view.selected = item.values[0]
            view.select_menu.options = view.refresh_options()
            await interaction.response.send_message(embed=embed, ephemeral=True, view=view)
            view.original_message = await interaction.original_message()
            
            del view
            return False

        return True
    
    async def on_timeout(self) -> None:
        self.disable_all()
        
        try:
            await self.original_message.edit(view=self)
        except discord.HTTPException:
            return
    
    def refresh_options(self):
        return [
            opt for opt in self.options if opt.value != self.selected
        ]
    
    async def get_embed(self, interaction: Interaction, *, ranking: str = None, cache: Dict[str, str] = None) -> discord.Embed:
        cache = cache or self.cache
        ranking = ranking or self.selected
        rankings = cache.get(ranking, None)
        
        if not rankings:
            rankings = await self.fetch_rankings(self.client.db, ranking, interaction.user.id)
            
            cache[ranking] = rankings
        
        embed = discord.Embed(
            title=f"global rankings for {ranking} score",
            description=rankings,
            colour=BotColours.cyan
        ).set_footer(
            icon_url=interaction.user.avatar.url,
            text="use the dropdown to view other rankings"
        )

        return embed
    
    @ui.select(placeholder="rank by...")
    async def select_menu(self, interaction: Interaction, select: ui.Select):
        await interaction.response.defer()
        self.selected = select.values[0]
        select.options = self.refresh_options()
        embed = await self.get_embed(interaction)
        
        await interaction.edit_original_message(embed=embed, view=self)
    
    @ui.button(label="(true width × true height)^1.1 ÷ (seconds + moves) ÷ 2.5")
    async def formula(self, interaction: Interaction, button: ui.Button):
        content = "\n".join([
            "**this the formula used to calculate ranking score.**",
            "",
            "when use terms like `true width` for example, we are referring to the how the width",
            "of the maze is stored internally. the width you enter when generating the maze",
            "is only the number of *path spaces* across, whilst *true width* refers to both the number of",
            "paths **and** walls across. therefore, __the true width and height of a `15x10` maze is `29x19`__.",
        ])
        
        await interaction.response.send_message(content, ephemeral=True)


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
        
        async def new_game(args: Any = None):
            if args is not None and args["started_at"]:
                q = """DELETE FROM mazes WHERE user_id = $1"""
                await self.client.db.execute(q, interaction.user.id)
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
                self.client, interaction.user.id, *settings, None, None, width, height, now, *zeroes, True
            )
            game.original_message = original_message
            self.client._mazes[interaction.user.id] = game
            
            await interaction.edit_original_message(
                content=None,
                attachments=[await self.client.loop.run_in_executor(None, game.to_file)],
                view=game
            )
            del args, game
        
        q = """SELECT *
                FROM settings
                FULL JOIN mazes
                ON mazes.user_id = settings.user_id
                WHERE mazes.user_id = $1 OR settings.user_id = $1
            """
        args: MazeGameEntry | None = await self.client.db.fetchrow(q, interaction.user.id)
        if args is not None and args["started_at"]:
            x, y = args["width"] // 2 + 1, args["height"] // 2 + 1
            last = "\n\n— **loaded saves do __not__ count for leaderboard points**" if not args["keep_ranked"] else ""
            embed = discord.Embed(
                title="save found",
                description=f"a previously saved **{x}x{y}** "
                             "maze has been found, load save or overwrite?"
                             f"{last}"
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
        del args
    
    @command(name="leaderboard")
    @describe(ranking="the score ranking to view. defaults to best score")
    @choices(ranking=[
        Choice(name="best score", value="best"),
        Choice(name="total score", value="total"),
        Choice(name="average score", value="average"),
    ])
    @checks.cooldown(1, 15)
    async def maze_leaderboard(self, interaction: Interaction, ranking: Choice[str] = "best"):
        """
        gets the global leaderboards for best, total, and average scores
        """
        
        await interaction.response.defer(thinking=True)
        if isinstance(ranking, Choice):
            ranking = ranking.value
        
        init_rankings = await Leaderboards.fetch_rankings(self.client.db, ranking, interaction.user.id)
        lb = Leaderboards(self.client, interaction.user.id, {ranking: init_rankings})
        lb.original_message = await interaction.original_message()
        
        embed = discord.Embed(
            title=f"global rankings for {ranking} score",
            description=init_rankings,
            colour=BotColours.cyan
        ).set_footer(
            icon_url=interaction.user.avatar.url,
            text="use the dropdown to view other rankings"
        )
        
        await interaction.edit_original_message(embed=embed, view=lb)
    
    @maze.error
    async def maze_error(self, interaction: Interaction, error: AppCommandError):
        if isinstance(error, MaxConcurrencyReached):
            return await interaction.response.send_message(
                "you already have a game going on\n"
                f"[jump to game](<{error.jump_url}>)",
                ephemeral=True
            )
    
    @maze_leaderboard.error
    async def maze_leaderboard_error(self, interaction: Interaction, error: AppCommandError):
        if isinstance(error, errors.CommandOnCooldown):
            return await interaction.response.send_message(
                f"this command is on cooldown, try again in `{error.retry_after:.2f}`s",
                ephemeral=True
            )


async def setup(client: Amaze):
    await client.add_cog(Mazes(client=client))
