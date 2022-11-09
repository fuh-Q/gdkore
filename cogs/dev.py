from __future__ import annotations

import math
import os
import pathlib
import sys
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from itertools import chain
from typing import Any, Coroutine, Generator, List, Tuple, TYPE_CHECKING

import discord
from discord.ext import commands
from discord.ui import Button, Select, button

from utils import (
    BasePages,
    cap
)

if TYPE_CHECKING:
    from discord import Interaction
    from discord.ui import Item

    from helper_bot import NotGDKID


Slicer = Generator[Tuple[pathlib.Path], None, None]

S = "\\" if sys.platform == "win32" else "/"

def size(size_in_bytes: int) -> str:
    """
    Converts a number of bytes to an appropriately-scaled unit
    E.g.:
        1024 -> 1.00 kilobytes
        12345678 -> 11.77 megabytes
    """
    if not size_in_bytes:
        return "0 bytes"

    units = (
        " bytes", "KiB", "MiB",
        "GiB", "TiB", "PiB",
        "EiB", "ZiB", "YiB"
    )

    power = int(math.log(size_in_bytes, 1024))

    return f"{(size_in_bytes / (1024 ** power)):.2f}{units[power]}"

class DirectoryView(BasePages):
    items: List[pathlib.Path]
    directory: pathlib.Path
    _directory_slices: List[Tuple[pathlib.Path]]
    _actual_files: Tuple[pathlib.Path]

    def __init__(
        self,
        directory: pathlib.Path,
        ctx: commands.Context | None = None,
        interaction: Interaction | None = None
    ):
        self.directory = directory
        self.items = sorted(directory.iterdir(), key=lambda k: k.name.lower())

        self._pages = []
        self._directory_slices = []
        self._current = 0
        self._parent = False
        if ctx:
            self._ctx = ctx
        elif interaction:
            self._interaction = interaction

        self.make_pages()

        super().__init__(timeout=self.TIMEOUT)
        self.update_components()

        self.select_menu = DirectoryPicker(self)
        self.add_item(self.select_menu)

        self.send_file = SendFile(self)
        self.send_file_ephemeral = SendFile(self, True)
        self.load_file = ExtensionButton(self, ExtensionAction.LOAD)
        self.unload_file = ExtensionButton(self, ExtensionAction.UNLOAD)
        self.reload_file = ExtensionButton(self, ExtensionAction.RELOAD)

        self.update_file_buttons()

    @property
    def slice_index(self) -> int:
        nslices = len(self._directory_slices)
        return self.current_page if self.current_page <= nslices - 1 else nslices - 1

    def make_pages(self) -> None:
        files = tuple(filter(lambda i: not i.is_dir(), self.items))
        directories = tuple(i for i in self.items if i not in files and
                            not i.name.startswith(".") and not i.name in ("venv", "__pycache__")
                            and len(str(i.resolve())) <= 100)
        self._actual_files = files
        self._pages = [discord.Embed(
            title=f"{cap(discord.utils.escape_markdown(f.name, as_needed=True)):256}",
            description= \
                f"file size - `{size(os.path.getsize(resolved := f.resolve()))}`\n" \
                f"file last modified - <t:{os.path.getmtime(str(resolved)):.0f}:R>",
            timestamp=datetime.now(tz=timezone.utc),
            url=f"https://fileinfo.com/extension/{f.parts[-1].split('.')[-1]}"
        ).set_author(name=f"{cap(str(f.resolve())):256}") for f in files]

        if not self._pages:
            self._pages.append(discord.Embed(
                description="no files to display"
            ).set_author(name=f"{cap(str(self.directory.resolve())):256}"))

        if len(directories) > 25:
            self._directory_slices = [s for s in self.slice_directories(directories)]
        else:
            self._directory_slices = [directories]

        if (slices := len(self._directory_slices)) > self.page_count:
            diff = slices - self.page_count
            self._pages += [discord.Embed(
                description="no files to display"
            ).set_author(name=f"{cap(str(self.directory.resolve())):256}") for _ in range(diff)]


    def slice_directories(self, directories: Tuple[pathlib.Path]) -> Slicer:
        chunk_size = 24
        l = len(directories)
        for idx in range(0, l, chunk_size):
            yield directories[idx:min(idx + chunk_size, l)]

    def get_select_options(self) -> List[discord.SelectOption]:
        opts = [discord.SelectOption(label=f"{cap(f.name):100}", value=str(f.resolve()))
                for f in self._directory_slices[self.slice_index]
                if not f.name.startswith(".") and not f.name in ("venv", "__pycache__")]

        opts.insert(0, discord.SelectOption(
            label="..",
            value=str(self.directory.parent.resolve())
        ))

        return opts

    def update_file_buttons(self) -> None:
        self.remove_item(self.send_file)
        self.remove_item(self.send_file_ephemeral)
        self.remove_item(self.remove_file)
        self.remove_item(self.load_file)
        self.remove_item(self.unload_file)
        self.remove_item(self.reload_file)

        if not self._actual_files:
            return

        file = self._actual_files[self.current_page]
        parent, filename = file.parts[-2:]
        if parent.endswith("cogs") and filename.endswith(".py"):
            ext = self.client.extensions.get(f"{parent}.{filename[:-3]}")
            if ext:
                self.add_item(self.unload_file)
                self.add_item(self.reload_file)
            else:
                self.add_item(self.load_file)

        if self.pages[self.current_page].title:
            self.add_item(self.send_file)
            self.add_item(self.send_file_ephemeral)
            self.add_item(self.remove_file)

    async def after_callback(self, interaction: Interaction, item: Item):
        if item.row != 0:
            return

        self.select_menu.options = self.get_select_options()
        self.update_file_buttons()

        if (nslices := self.slice_index) == self.current_page:
            page = self.current_page
        else:
            page = len(self._directory_slices) - 1
        self.select_menu.placeholder = self.select_menu.get_placeholder(page)

        self.update_components()
        await interaction.edit_original_response(**self.edit_kwargs)

    @button(label="remove file", style=discord.ButtonStyle.danger, row=2)
    async def remove_file(self, interaction: Interaction, button: Button):
        self._actual_files[self.current_page].unlink(missing_ok=True)

        await interaction.response.send_message("file removed", ephemeral=True)

class SendFile(Button[DirectoryView]):
    _view: DirectoryView

    @property
    def view(self) -> DirectoryView:
        return self._view

    def __init__(self, view: DirectoryView, send_ephemeral: bool = False):
        self._view = view
        self.send_ephemeral = send_ephemeral

        super().__init__(
            label="send file",
            style=discord.ButtonStyle.primary,
            row=2
        )

        if send_ephemeral:
            assert self.label
            self.label += " (ephemeral)"

    async def callback(self, interaction: Interaction) -> None:
        await interaction.response.defer()

        try:
            path = self.view._actual_files[self.view.current_page].resolve()
            file = discord.File(str(path), filename=path.name)
        except FileNotFoundError as e:
            return await interaction.followup.send(
                embed=discord.Embed(description=f"```py\n{e}\n```"), ephemeral=True
            )

        try:
            await interaction.followup.send(file=file, ephemeral=self.send_ephemeral)
        except discord.HTTPException as e:
            if e.status == 413:
                return await interaction.followup.send(
                    "file size exceeds upload limit", ephemeral=True
                )

            raise e

class ExtensionAction(Enum):
    value: Tuple[str, Coroutine[Any, Any, None]]

    LOAD = ("load as extension", commands.Bot.load_extension)
    UNLOAD = ("unload extension", commands.Bot.unload_extension)
    RELOAD = ("reload extension", commands.Bot.reload_extension)

class ExtensionButton(Button[DirectoryView]):
    _view: DirectoryView

    @property
    def view(self) -> DirectoryView:
        return self._view

    def __init__(self, view: DirectoryView, button_action: ExtensionAction):
        self._view = view

        label, method = button_action.value
        super().__init__(
            label=label,
            style=discord.ButtonStyle.success,
            row=3
        )
        self.method: partial[Coroutine[Any, Any, None]] = partial(method, view.client) # type: ignore

    async def callback(self, interaction: Interaction) -> None:
        folder, name = self.view._actual_files[self.view.current_page].resolve().parts[-2:]

        try:
            await self.method(f"{folder}.{name[:-3]}")
        except commands.ExtensionError as e:
            em = discord.Embed(title="FUCK!", description=f"```py\n{e}\n```")
            return await interaction.response.send_message(embed=em, ephemeral=True)
        else:
            assert self.label
            self.view.update_file_buttons()
            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send(
                f"{self.label.split(' ')[0]}ed `{folder}.{name[:-3]}`", ephemeral=True
            )

class DirectoryPicker(Select[DirectoryView]):
    _view: DirectoryView

    @property
    def view(self) -> DirectoryView:
        return self._view

    def __init__(self, view: DirectoryView):
        self._view = view

        super().__init__(
            placeholder=self.get_placeholder(self.view.current_page),
            min_values=1,
            max_values=1,
            options=self.view.get_select_options()
        )

        if not self.options:
            self.options = [discord.SelectOption(label="sadge")]
            self.disabled = True

    def get_placeholder(self, page: int) -> str:
        slices = self.view._directory_slices
        total = len(tuple(chain.from_iterable(slices))) + len(slices)
        if total > 25:
            start = 25 * page + 1
            stop = start + len(self.view._directory_slices[self.view.slice_index])
        else:
            start = 1
            stop = total

        return f"{cap(f'change directories... [{start}-{stop} of {total}]'):150}"

    async def callback(self, interaction: Interaction) -> None:
        try:
            view = DirectoryView(pathlib.Path(self.values[0]), interaction=interaction)
        except (FileNotFoundError, PermissionError) as e:
            em = discord.Embed(title="FUCK!", description=f"```py\n{e}\n```")
            return await interaction.response.send_message(embed=em, ephemeral=True)

        await interaction.response.edit_message(
            embed=view.pages[0],
            view=view
        )

        self.view.stop()
        del self._view, self


class Dev(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client
        self.emoji = "<a:gdkid:868976838112841760>"

    @commands.command(name="files")
    @commands.is_owner()
    async def files(self, ctx: commands.Context):
        view = DirectoryView(pathlib.Path(os.getcwd()), ctx)

        view.original_message = await ctx.reply(embed=view.pages[0], view=view)

    @commands.command(
        name="guilds", aliases=["servers"], hidden=True, brief="Get the bot's server count"
    )
    @commands.is_owner()
    async def guilds(self, ctx: commands.Context):
        command = self.client.get_command("repl exec")
        await ctx.invoke(
            command, # type: ignore
            code='"".join(["\\n".join(["{0.name}: {1} members | {0.id}".format(g, len([m for m in g.members if not m.bot])) for g in client.guilds]), f"\\n\\n{len(client.guilds):.2f} servers"])', # type: ignore
        )

    @commands.command(name="shutdown", hidden=True, brief="Shut down the bot")
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        e = discord.Embed(description="👋 cya")
        await ctx.reply(embed=e)

        await self.client.close()

    @commands.command(name="restart", hidden=True, brief="Restart the bot")
    @commands.is_owner()
    async def restart(self, ctx: commands.Context):
        e = discord.Embed(description="👋 Aight brb")
        await ctx.reply(embed=e)

        await self.client.close(restart=True)

    @commands.command(name="hi", brief='Say "Hi" to the bot', hidden=True)
    @commands.is_owner()
    async def hi(self, ctx: commands.Context):
        await ctx.reply("hi")


async def setup(client: NotGDKID):
    await client.add_cog(Dev(client=client))
