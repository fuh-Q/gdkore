from __future__ import annotations

import asyncio
import io
import math
import os
import pathlib
import sys
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from itertools import chain
from typing import Any, Coroutine, Generator, List, Tuple, TYPE_CHECKING
from zipfile import ZipFile, ZIP_DEFLATED as zip_comp

import discord
from discord.ext import commands
from discord.ui import Button, Modal, Select, TextInput, button

from utils import BasePages, BotEmojis, Confirm, Embed, cap

if TYPE_CHECKING:
    from discord import Interaction
    from discord.ui import Item

    from helper_bot import NotGDKID
    from utils import NGKContext


ExtCoro = Coroutine[Any, Any, None]
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

    units = (" bytes", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")

    power = int(math.log(size_in_bytes, 1024))

    return f"{(size_in_bytes / (1024 ** power)):.2f}{units[power]}"


class DirectoryView(BasePages):
    items: List[pathlib.Path]
    directory: pathlib.Path
    _directory_slices: List[Tuple[pathlib.Path]]
    _actual_files: List[pathlib.Path]

    EXCLUDED_DIRS = ("__pycache__",)

    def __init__(self, directory: pathlib.Path, ctx: commands.Context | None = None, interaction: Interaction | None = None):
        self.directory = directory.resolve()
        self.items = sorted(map(lambda item: item.resolve(), directory.iterdir()), key=lambda k: k.name.lower())

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

        self.load_file = ExtensionButton(self, ExtensionAction.LOAD)
        self.unload_file = ExtensionButton(self, ExtensionAction.UNLOAD)
        self.reload_file = ExtensionButton(self, ExtensionAction.RELOAD)

        self.update_file_buttons()

    @property
    def slice_index(self) -> int:
        nslices = len(self._directory_slices)
        return self.current_page if self.current_page <= nslices - 1 else nslices - 1

    def make_pages(self) -> None:
        files = list(filter(lambda i: not i.is_dir(), self.items))
        directories = tuple(
            i for i in self.items if i not in files and not i.name in self.EXCLUDED_DIRS and len(str(i)) <= 100
        )
        self._actual_files = files
        self._pages = [
            Embed(
                title=f"{cap(discord.utils.escape_markdown(f.name, as_needed=True)):256}",
                description=f"file size - `{size(os.path.getsize(f))}`\n"
                f"file last modified - <t:{os.path.getmtime(str(f)):.0f}:R>",
                timestamp=datetime.now(tz=timezone.utc),
                url=f"https://fileinfo.com/extension/{f.parts[-1].split('.')[-1]}",
            ).set_author(name=f"{cap(str(f)):256}")
            for f in files
        ]

        if not self._pages:
            self._pages.append(Embed(description="no files to display").set_author(name=f"{cap(str(self.directory)):256}"))

        if len(directories) > 25:
            self._directory_slices = [s for s in self.slice_directories(directories)]
        else:
            self._directory_slices = [directories]

        slices = len(self._directory_slices)
        if slices > self.page_count:
            diff = slices - self.page_count
            self._pages += [
                Embed(description="no files to display").set_author(name=f"{cap(str(self.directory)):256}")
                for _ in range(diff)
            ]

    def slice_directories(self, directories: Tuple[pathlib.Path]) -> Slicer:
        chunk_size = 24
        l = len(directories)
        for idx in range(0, l, chunk_size):
            yield directories[idx : min(idx + chunk_size, l)]

    def get_select_options(self) -> List[discord.SelectOption]:
        opts = []
        values = set()
        for f in self._directory_slices[self.slice_index]:
            if not f.name in self.EXCLUDED_DIRS and str(f) not in values:
                values.add(str(f))
                opts.append(discord.SelectOption(label=f"{cap(f.name):100}", value=str(f)))

        opts.insert(0, discord.SelectOption(label="..", value=str(self.directory.parent)))

        return opts

    def update_file_buttons(self) -> None:
        self.remove_item(self.send_file)
        self.remove_item(self.rename_file)
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
            self.add_item(self.rename_file)
            self.add_item(self.remove_file)

    async def after_callback(self, interaction: Interaction, item: Item):
        if item.row != 0:
            return

        self.select_menu.options = self.get_select_options()
        self.update_file_buttons()

        if self.slice_index == self.current_page:
            page = self.current_page
        else:
            page = len(self._directory_slices) - 1
        self.select_menu.placeholder = self.select_menu.get_placeholder(page)

        self.update_components()
        await interaction.edit_original_response(**self.edit_kwargs)

    async def prompt_ephemeral(self, interaction: Interaction) -> Tuple[bool | None, Confirm]:
        await interaction.response.defer(ephemeral=True)

        view = Confirm(interaction.user, add_third=True, third_label="cancel")
        embed = Embed(description="would you like to have this item sent **ephemerally**?")
        msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.original_message = msg

        expired = await view.wait()
        if expired:
            return None, view

        await view.interaction.response.defer()
        if not view.choice:
            await interaction.followup.delete_message(msg.id)

        return view.choice, view

    async def try_send_item(
        self,
        interaction: Interaction,
        view: Confirm,
        directory: bool,
        ephemeral: bool,
    ) -> None:
        def zip_creator(buffer: io.BytesIO):
            with ZipFile(buffer, "a", compression=zip_comp) as f:
                for item in self.directory.iterdir():
                    if not item.is_dir():
                        try:
                            f.writestr(item.name, item.read_bytes())
                        except PermissionError:
                            continue

            buffer.seek(0)
            return buffer

        buffer = None
        try:
            if not directory:
                path = self._actual_files[self.current_page]
                file = discord.File(str(path), filename=path.name)
            else:
                if ephemeral is True:
                    e = discord.Embed(description=f"{BotEmojis.LOADING} working on it...")
                    await view.interaction.edit_original_response(embed=e, view=None)

                assert isinstance(interaction.channel, discord.TextChannel)
                async with interaction.channel.typing():
                    buffer = await asyncio.to_thread(zip_creator, io.BytesIO())
                    file = discord.File(buffer, filename=f"{self.directory.name}.zip")
        except FileNotFoundError as e:
            return await interaction.followup.send(embed=Embed(description=f"```py\n{e}\n```"), ephemeral=True)
        finally:
            if buffer is not None and not buffer.closed:
                buffer.close()

        method, kwargs = (
            (view.interaction.edit_original_response, {"attachments": [file], "embed": None, "view": None})
            if ephemeral is True
            else (view.interaction.followup.send, {"file": file})
        )

        try:
            await method(**kwargs)
        except discord.HTTPException as e:
            if e.status == 413:
                extras = {"embed": None} if ephemeral is True else {}
                await method(content="entity exceeds file upload limit", **extras)
                return

            raise e

    @button(label="send file", style=discord.ButtonStyle.primary, row=2)
    async def send_file(self, interaction: Interaction, button: Button):
        choice, view = await self.prompt_ephemeral(interaction)
        if choice is None:
            return

        await self.try_send_item(interaction, view, directory=False, ephemeral=choice)

    @button(label="all files (zip)", style=discord.ButtonStyle.primary, row=2)
    async def send_all_files(self, interaction: Interaction, button: Button):
        choice, view = await self.prompt_ephemeral(interaction)
        if choice is None:
            return

        await self.try_send_item(interaction, view, directory=True, ephemeral=choice)

    @button(label="rename file", style=discord.ButtonStyle.secondary, row=2)
    async def rename_file(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(RenameFile(self))

    @button(label="remove file", style=discord.ButtonStyle.danger, row=2)
    async def remove_file(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        view = Confirm(interaction.user)

        filename = self._actual_files[self.current_page].name
        embed = Embed(description=f"confirm that you want to delete `{cap(filename):4000}`?")
        msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.original_message = msg

        expired = await view.wait()
        if expired:
            await view.original_message.edit(view=view)
            return

        await interaction.followup.delete_message(msg.id)
        if not view.choice:
            return

        self.pages.pop(self.current_page)
        self._actual_files.pop(self.current_page).unlink(missing_ok=True)
        if self.current_page > 0:
            self._current -= 1

        if not self._actual_files:
            return await view.interaction.response.edit_message(embed=Embed(description="no files to display"), view=self)

        self.update_components()
        await view.interaction.response.edit_message(**self.edit_kwargs)


class RenameFile(Modal):
    name = TextInput(label="new name", placeholder="example.txt", max_length=100)

    def __init__(self, view: DirectoryView) -> None:
        self._view = view
        self._file = view._actual_files[view.current_page]
        self._page = view.pages[view.current_page]

        self.name.default = self._file.name
        super().__init__(title="rename file")

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        embed = Embed(title="FUCK!", description=f"```py\n{error}\n```")
        await interaction.response.send_message(embed=embed)

    async def on_submit(self, interaction: Interaction) -> None:
        self._file = self._file.rename(f"{self._file.parts[0]}{S.join(self._file.parts[1:-1])}{S}{self.name.value}")

        self._view._actual_files[self._view.current_page] = self._file

        fp = cap(str(self._file))
        title = cap(discord.utils.escape_markdown(self._file.name, as_needed=True))
        self._page.set_author(name=f"{fp:256}").title = f"{title:256}"
        await interaction.response.edit_message(embed=self._page)


class ExtensionAction(Enum):
    value: Tuple[str, ExtCoro]

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
        super().__init__(label=label, style=discord.ButtonStyle.success, row=3)
        self.method: partial[ExtCoro] = partial(method, view.client)  # type: ignore

    async def callback(self, interaction: Interaction) -> None:
        folder, name = self.view._actual_files[self.view.current_page].parts[-2:]

        try:
            await self.method(f"{folder}.{name[:-3]}")
        except commands.ExtensionError as e:
            em = Embed(title="FUCK!", description=f"```py\n{e}\n```")
            return await interaction.response.send_message(embed=em, ephemeral=True)
        else:
            assert self.label
            self.view.update_file_buttons()
            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send(f"{self.label.split(' ')[0]}ed `{folder}.{name[:-3]}`", ephemeral=True)


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
            options=self.view.get_select_options(),
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
            em = Embed(title="FUCK!", description=f"```py\n{e}\n```")
            return await interaction.response.send_message(embed=em, ephemeral=True)

        await interaction.response.edit_message(embed=view.pages[0], view=view)

        self.view.stop()
        del self._view, self


class Dev(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client
        self.emoji = "<a:gdkid:868976838112841760>"

    @commands.command(name="files", hidden=True)
    @commands.is_owner()
    async def files(self, ctx: NGKContext):
        view = DirectoryView(pathlib.Path(os.getcwd()), ctx)

        view.original_message = await ctx.reply(embed=view.pages[0], view=view)

    @commands.command(name="blacklist", aliases=["bl"], hidden=True)
    @commands.is_owner()
    async def blacklist(self, ctx: NGKContext, obj: discord.Object):
        await self.client.blacklist.put(obj.id, True)
        guild = self.client.get_guild(obj.id)
        if guild is not None:
            await guild.leave()

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="unblacklist", aliases=["ubl"], hidden=True)
    @commands.is_owner()
    async def unblacklist(self, ctx: NGKContext, obj: discord.Object):
        await self.client.blacklist.remove(obj.id, missing_ok=True)
        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="guilds", aliases=["servers"], hidden=True, brief="Get the bot's server count")
    @commands.is_owner()
    async def guilds(self, ctx: NGKContext):
        command = self.client.get_command("repl exec")
        await ctx.invoke(
            command,  # type: ignore
            code='"".join(["\\n".join(["{0.name}: {1} members | {0.id}".format(g, len([m for m in g.members if not m.bot])) for g in client.guilds]), f"\\n\\n{len(client.guilds):.2f} servers"])',  # type: ignore
        )

    @commands.command(name="shutdown", hidden=True, brief="Shut down the bot")
    @commands.is_owner()
    async def shutdown(self, ctx: NGKContext):
        e = Embed(description="👋 cya")
        await ctx.reply(embed=e)

        await self.client.close()

    @commands.command(name="restart", hidden=True, brief="Restart the bot")
    @commands.is_owner()
    async def restart(self, ctx: NGKContext):
        e = Embed(description="👋 Aight brb")
        await ctx.reply(embed=e)

        await self.client.close(restart=True)

    @commands.command(name="hi", brief='Say "Hi" to the bot', hidden=True)
    @commands.is_owner()
    async def hi(self, ctx: NGKContext):
        await ctx.reply("hi")


async def setup(client: NotGDKID):
    await client.add_cog(Dev(client=client))
