from __future__ import annotations

import discord
from discord import ui
from discord.ext import commands
from discord.app_commands import (
    AppCommandError,
    Choice,
    CheckFailure,
    Cooldown,
    Range,
    autocomplete,
    command,
    checks,
    describe,
)

import asyncio
from io import BytesIO
import time
from datetime import datetime, timezone
from typing import Any, ClassVar, Callable, Coroutine, Dict, List, Sequence, Tuple, TypedDict, TypeVar, TYPE_CHECKING

import maze
from utils import AsyncInit, BasePages, BotEmojis, BotColours, MaxConcurrencyReached, View, humanize_timedelta

if TYPE_CHECKING:
    from bot import Amaze

    from typing_extensions import Unpack

    XY = Direction = Tuple[int, int]
    Rgb = Tuple[int, int, int]
    Rgba = Tuple[int, int, int, int]
    T = TypeVar("T")
    Coro = Coroutine[Any, Any, T]
    Interaction = discord.Interaction[Amaze]

_active_games: Dict[int, str | None] = {}

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
ZERO_ZERO = (0, 0)

# any maze larger than 100*100 in area
# clicking a move button will have its interaction deferred first
MOVE_DEFER_THRESHOLD = 100 * 100
MAX_MAZE_SIZE = 200 * 200
MAZE_FILE = "maze.png"

DIRECTION_NAME = {
    maze.LEFT: "LEFT",
    maze.UP: "UP",
    maze.DOWN: "DOWN",
    maze.RIGHT: "RIGHT",
}

TUTORIAL = """
so if this is your first time doing this...

- your goal is to get to the bottom right corner, and you can move around by clicking the buttons below
- the first row of buttons move you one space over in whichever direction you clicked
- the second row of buttons move you the furthest possible distance in a direction until you hit a wall
- in order to change this text, you can run `/mazeconfig title`, and set the `text` argument accordingly
- if you want to remove this text altogether, you can run that same command, but without arguments
""".strip()


class MazeTooBig(CheckFailure):
    shpeal = (
        "this is a very bad idea. very *very* not good. let's just say that an image of that size "
        "is literally so large that Discord won't even bother showing a preview (see image below)\n"
        "i'm sure you have some amazing maze solving skills that rival even the best of OpenAI models, "
        "however those skills will mean absolutely nothing considering that this image "
        "will literally genuinely legitametely take *forever* to upload to Discord\n"
        "and that's only the initial maze generation, we're not even talking about every individual move "
        "where we need to edit the image and RE-UPLOAD *THAT* to Discord as well\n"
        "if you somehow do end up getting a preview, it will be crunched down so much so that the paths are "
        "completely undiscernable, and thus the maze is completely unplayable\n\n"
        "thank you for reading my ted talk"
    )


class MazeParams(TypedDict):
    bg_colour: Rgb | Rgba
    wall_colour: Rgb | Rgba
    solution_colour: Rgb | Rgba
    player: bytes | None
    endzone: bytes | None
    width: int
    height: int


class PerfectRunDirections(BasePages, auto_defer=False):
    MOVES_PER_PAGE: ClassVar[int] = 15
    last_interaction: Interaction

    def __init__(self, interaction: Interaction, directions: Sequence[str]):
        self._pages = []
        self._current = 0
        self._parent = False
        self._interaction = interaction

        super().__init__(timeout=self.TIMEOUT)

        self.directions_to_pages(directions=directions)
        self.update_components()

    def directions_to_pages(self, *, directions: Sequence[str]):
        items = [i for i in directions]
        offset = 0

        while items != []:
            bundle = items[: self.MOVES_PER_PAGE]
            # fmt: off
            desc = "\n".join(
                f"{s[0]} {s[1]+' '+s[2]:<10} {s[3]}"
                for s in (d.split() for d in bundle)
            )  # fmt: on

            current_page = offset // self.MOVES_PER_PAGE + 1
            e = discord.Embed(description=f"```ocaml\n{desc}```")
            e.set_footer(text=f"page {current_page}/{self.page_count}")
            self._pages.append(e)

            offset += self.MOVES_PER_PAGE
            items = items[self.MOVES_PER_PAGE :]

    async def after_callback(self, interaction: Interaction, item: ui.Item):
        self.update_components()
        await interaction.response.edit_message(**self.edit_kwargs)


class GameEndedMenu(View, auto_defer=True):
    last_interaction: Interaction

    def __init__(self, owner_id: int, directions: Sequence[str]):
        self._owner_id = owner_id
        self._directions = directions

        super().__init__(timeout=self.TIMEOUT)

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        return True

    async def on_timeout(self) -> None:
        self.clear_items()

        try:
            await self.last_interaction.edit_original_response(view=self)
        except discord.HTTPException:
            pass  # we tried

    @ui.button(label="view a perfect run", style=discord.ButtonStyle.secondary)
    async def perfect_run(self, interaction: Interaction, button: ui.Button):
        menu = PerfectRunDirections(interaction, self._directions)
        await menu.start()


class MoveButton(ui.Button):
    view: Game

    def __init__(self, direction: Direction, emoji_ident: str, move_max: bool):
        row = int(move_max)
        self.direction = direction
        emoji = getattr(BotEmojis, f"MAZE_{emoji_ident}_{row+1}")

        super().__init__(row=row, emoji=emoji)

    async def callback(self, interaction: Interaction) -> Any:
        coords = self.view.coords
        direction = self.direction
        if self.row == 1:  # move max
            self.view.coords = self.view.maze.move_max(coords, direction)
            return

        # normal move
        new_coords = (coords[0] + direction[0], coords[1] + direction[1])
        if not self.view.maze.has_wall_between(self.view.coords, new_coords):
            self.view.coords = new_coords


class Game(View, metaclass=AsyncInit, auto_defer=False):
    last_interaction: Interaction

    async def __init__(
        self, *, owner_id: int, title: str | None, start_coords: XY | None = None, **params: Unpack[MazeParams]
    ):
        self._owner_id = owner_id

        self._player_coords = start_coords or ZERO_ZERO
        self._title = title
        self._move_count = 0
        self._start_time = datetime.now(tz=timezone.utc)
        self._width = params["width"]
        self._height = params["height"]

        self.maze = await asyncio.to_thread(maze.generate_maze, **params)
        self.maze.draw_player_at(start_coords or ZERO_ZERO)

        super().__init__(timeout=self.TIMEOUT)

        og_children = self.children  # makes a shallow copy
        self.clear_items()

        for k, v in DIRECTION_NAME.items():
            self.add_item(MoveButton(k, v, False))
            self.add_item(MoveButton(k, v, True))

        for item in og_children:
            self.add_item(item)

        self.update_components()

    @property
    def coords(self) -> XY:
        return self._player_coords

    @coords.setter
    def coords(self, new: XY):
        self._player_coords = new

    @property
    def title(self) -> str | None:
        return self._title

    async def on_timeout(self) -> None:
        self.disable_all()

        content = (
            f"ok im guessing you just {BotEmojis.PEACE}'d out on me "
            f"since you havent clicked anything for {humanize_timedelta(seconds=self.timeout)} "
            f"<@!{self._owner_id}>\n\n"
        )

        try:
            await self.last_interaction.edit_original_response(content=content, view=self)
        except discord.HTTPException:  # race condition with the forfeit button being pressed
            pass

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if interaction.user.id != self._owner_id:
            await interaction.response.send_message(
                content="it's not your game, you can start one by running `/maze`", ephemeral=True
            )

            return False

        interaction.extras["original_coords"] = self.coords
        self.last_interaction = interaction
        return True

    async def after_callback(self, interaction: Interaction, item: ui.Item):
        if interaction.response.is_done():
            return  # they hit the forfeit button
        elif self._width * self._height > MOVE_DEFER_THRESHOLD:
            self.disable_all()
            await interaction.response.edit_message(view=self)
            edit_method = interaction.edit_original_response
        else:
            edit_method = interaction.response.edit_message

        self._move_count += 1
        if item.row == 0:
            self.maze.undraw_at(interaction.extras["original_coords"])
            self.maze.draw_player_at(self.coords)

        image = await asyncio.to_thread(self.maze.get_image_expensively)
        if self.coords == (self._width - 1, self._height - 1):
            self.disable_all()
            self.stop()

            return await self.on_player_win(edit_method, image)

        self.update_components()
        await edit_method(content=self.title, attachments=[discord.File(image, filename=MAZE_FILE)], view=self)

    async def on_player_win(self, edit_method: Callable[..., Any], image: BytesIO):
        rn = datetime.now(tz=timezone.utc)
        taken = humanize_timedelta(delta=rn - self._start_time)
        self.maze.compute_solution(draw_path=False)
        (n_moves, directions) = await asyncio.to_thread(self.maze.get_solution_expensively)

        bottom = (
            "you did a perfect run, nice job!"
            if self._move_count == n_moves
            else f"a perfect run would've taken `{n_moves}` moves, click the button below for more\N{HORIZONTAL ELLIPSIS}"
        )

        content = (
            "**you finished!**\n\n"
            f"— total time `{taken}`\n"
            f"— moves `{self._move_count}`\n\n"
            f"\N{HANGUL FILLER}*{bottom}*\n\u200b"
        )

        if self.title:
            content += f"\n——————————\n{self.title}"

        menu = GameEndedMenu(self._owner_id, directions)
        menu.last_interaction = self.last_interaction
        await edit_method(content=content, attachments=[discord.File(image, filename=MAZE_FILE)], view=menu)

    def stop(self):
        _active_games.pop(self._owner_id, None)
        super().stop()

    def update_components(self):
        self.forfeit.disabled = False  # the calls to `self.disable_all()` will inadvertently snag this one too

        for button in self.children[:8]:
            assert isinstance(button, MoveButton)

            direction = button.direction
            new_coords = (self.coords[0] + direction[0], self.coords[1] + direction[1])
            button.disabled = self.maze.has_wall_between(self.coords, new_coords)

    @ui.button(emoji=BotEmojis.QUIT_GAME, style=discord.ButtonStyle.danger)
    async def forfeit(self, interaction: Interaction, button: ui.Button):
        self.stop()
        if self._width * self._height > MOVE_DEFER_THRESHOLD:
            self.disable_all()
            await interaction.response.edit_message(view=self)
            edit_method = interaction.edit_original_response
        else:
            edit_method = interaction.response.edit_message

        start = time.perf_counter()
        self.maze.compute_solution(draw_path=True)
        (n_moves, solution) = await asyncio.to_thread(self.maze.get_solution_expensively)
        compute_time = time.perf_counter() - start

        content = (
            "yep, fuck it\n\n"
            f"although was it *really* that hard? "
            f"it only took me `{round(compute_time, 5)}s` to compute the solution...\n"
            f"(not including the time it takes to edit this message, re-upload the image to Discord etc)\n\n"
            f"you can view a perfect run done in `{n_moves}` moves using the button below\n\u200b"
        )

        if self.title:
            content += f"\n——————————\n{self.title}"

        image = await asyncio.to_thread(self.maze.get_image_expensively)
        menu = GameEndedMenu(self._owner_id, directions=solution)
        menu.last_interaction = interaction

        await edit_method(content=content, attachments=[discord.File(image, filename=MAZE_FILE)], view=menu)


# this is pretty much what the private type `AutocompleteCallback` in `discord.app_commands.commands` unravels into
def default_suggest(n: int, /) -> Callable[..., Coro[List[Choice[int]]]]:
    """constant value for the autocomplete (they're only hinting at the user what to enter)"""

    async def wrapped(i, c):
        return [Choice(name=f"Default {n} (or enter your own value)", value=n)]

    return wrapped


def maze_cooldown(interaction: Interaction):
    if interaction.user.id not in interaction.client.owner_ids:
        return Cooldown(1, 3)


class Mazes(commands.Cog):
    def __init__(self, client: Amaze):
        self.client = client

    async def _fetch_settings(self, user_id: int, /) -> Dict[str, Any]:
        query = "SELECT * FROM maze_settings WHERE user_id = $1"
        result = await self.client.db.fetchrow(query, user_id)
        if result is not None:
            result = dict(result)

        return result or {
            "user_id": user_id,
            "bg_colour": BLACK,
            "wall_colour": WHITE,
            "solution_colour": RED,
            "player": None,
            "endzone": None,
            "title": TUTORIAL,
        }

    @command(name="maze")
    @describe(width="the width of the maze (default 20)", height="the height of the maze (default 15)")
    @checks.dynamic_cooldown(maze_cooldown)
    @autocomplete(width=default_suggest(20), height=default_suggest(15))
    async def maze(self, interaction: Interaction, width: Range[int, 2], height: Range[int, 2]):
        """
        generates a maze puzzle with the given width and height
        """

        if interaction.user.id in _active_games and interaction.user.id not in self.client.owner_ids:
            raise MaxConcurrencyReached(_active_games[interaction.user.id])

        if width * height > MAX_MAZE_SIZE:
            raise MazeTooBig

        _active_games[interaction.user.id] = None
        await interaction.response.send_message("building maze...")

        settings = await self._fetch_settings(interaction.user.id)
        game: Game = await Game(
            owner_id=settings.pop("user_id"),
            title=settings.pop("title", None),
            start_coords=ZERO_ZERO,
            width=width,
            height=height,
            **settings,
        )

        game.last_interaction = interaction
        image = await asyncio.to_thread(game.maze.get_image_expensively)
        msg = await interaction.edit_original_response(
            content=game.title, attachments=[discord.File(image, filename=MAZE_FILE)], view=game
        )

        _active_games[interaction.user.id] = msg.jump_url

    @maze.error
    async def maze_error(self, interaction: Interaction, error: AppCommandError):
        if isinstance(error, MaxConcurrencyReached):
            msg = "you already have a game going on"
            end_jump = f"\n[jump to game](<{error.jump_url}>)"
            end_fallback = "\n(it's still generating, give it a moment...)"

            return await interaction.response.send_message(
                msg + (end_jump if error.jump_url is not None else end_fallback),
                ephemeral=True,
            )
        if isinstance(error, checks.CommandOnCooldown):
            return await interaction.response.send_message(
                f"you're on cooldown, wait `{error.retry_after:.2f}s`",
                ephemeral=True,
            )
        if isinstance(error, MazeTooBig):
            embed = discord.Embed(
                title=f"NO!!!!!!!!!!!!!!!!!!!!!!!!!!!!{' NO'*75}\N{HORIZONTAL ELLIPSIS}",
                description=error.__class__.shpeal,
                colour=BotColours.red,
            )

            embed.set_image(url="https://i.vgy.me/bg6Weh.png")
            embed.set_footer(text="me when no preview")
            return await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )


async def setup(client: Amaze):
    await client.add_cog(Mazes(client=client))
