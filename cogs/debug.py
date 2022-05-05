import asyncio
import inspect
import io
import math
import os
import pathlib
import random
import re
import sys

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from jishaku.codeblocks import Codeblock, codeblock_converter
from jishaku.cog import OPTIONAL_FEATURES, STANDARD_FEATURES
from jishaku.features.baseclass import Feature
from jishaku.features.filesystem import guess_file_traits
from jishaku.features.python import (AsyncCodeExecutor, AsyncSender,
                                     all_inspections, disassemble,
                                     get_var_dict_from_ctx)
from jishaku.features.shell import ReplResponseReactor
from jishaku.flags import Flags
from jishaku.hljs import get_language
from jishaku.modules import package_version
from jishaku.paginators import WrappedFilePaginator, WrappedPaginator
from jishaku.shell import ShellReader as ShellReader
from jishaku.shim.paginator_200 import \
    PaginatorInterface as OGPaginatorInterface

from bot import NotGDKID
from config.utils import *

try:
    import psutil
except ImportError:
    psutil = None

JISHAKU_HIDE = Flags.HIDE
JISHAKU_FORCE_PAGINATOR = Flags.FORCE_PAGINATOR
JISHAKU_NO_DM_TRACEBACK = Flags.NO_DM_TRACEBACK
JISHAKU_RETAIN = Flags.RETAIN
JISHAKU_NO_UNDERSCORE = Flags.NO_UNDERSCORE
JISHAKU_USE_BRAILLE_J = Flags.USE_BRAILLE_J
SCOPE_PREFIX = Flags.SCOPE_PREFIX


def natural_size(size_in_bytes: int) -> str:
    """
    Converts a number of bytes to an appropriately-scaled unit
    E.g.:
        1024 -> 1.00 KiB
        12345678 -> 11.77 MiB
    """
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")

    power = int(math.log(size_in_bytes, 1024))

    return f"{size_in_bytes / (1024 ** power):.2f} {units[power]}"


class PaginatorInterFace(OGPaginatorInterface):
    button_start: discord.ui.Button
    button_previous: discord.ui.Button
    button_current: discord.ui.Button
    button_next: discord.ui.Button
    button_last: discord.ui.Button
    button_close: discord.ui.Button

    def __init__(
        self,
        bot: commands.Bot,
        paginator: commands.Paginator,
        **kwargs,
    ):
        try:
            bot.active_jishaku_paginators.append(self)

        except AttributeError:
            pass

        super().__init__(bot, paginator, **kwargs)

    def update_view(self):
        self.button_start.label = "❮❮❮"
        self.button_previous.label = "❮"
        self.button_current.label = f"{self.display_page + 1} / {self.page_count}"
        self.button_current.disabled = True
        self.button_next.label = "❯"
        self.button_last.label = f"❯❯❯"
        self.button_close.label = "✖"

        for child in self.children:
            try:
                child.emoji = None
            except Exception:
                pass

        if self.page_count < 2:
            self.button_goto.disabled = True

        if self.display_page == self.page_count - 1:
            self.button_last.disabled = True
            self.button_next.disabled = True

        else:
            self.button_last.disabled = False
            self.button_next.disabled = False

        if self.display_page == 0:
            self.button_start.disabled = True
            self.button_previous.disabled = True

        else:
            self.button_start.disabled = False
            self.button_previous.disabled = False

    async def send_to(self, destination: discord.abc.Messageable):
        self.update_view()

        return await super().send_to(destination)

    async def interaction_check(self, interaction: discord.Interaction):
        """Check that determines whether this interaction should be honored"""
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()
        self.message: discord.Message
        await self.message.edit(view=None)
        return

    def stop(self):
        self.bot.active_jishaku_paginators.pop(self.bot.active_jishaku_paginators.index(self))
        super().stop()

    def __setattr__(self, __name: str, __value) -> None:
        if __name == "close_exception" and __value is not None:
            try:
                self.bot.active_jishaku_paginators.pop(self.bot.active_jishaku_paginators.index(self))
            except ValueError:
                pass

        return super().__setattr__(__name, __value)


class Jishaku(*OPTIONAL_FEATURES, *STANDARD_FEATURES):

    """
    Jishaku but less weird
    """

    __cat_line_regex = re.compile(r"(?:\.\/+)?(.+?)(?:#L?(\d+)(?:\-L?(\d+))?)?$")
    bot: NotGDKID

    @Feature.Command(
        name="battler",
        aliases=["gdk"],
        hidden=JISHAKU_HIDE,
        invoke_without_command=True,
        ignore_extras=False,
        brief="Ban Battler debugging commands",
        help="**Checks**\nBot Owner",
    )
    @commands.is_owner()
    async def _jsk(self, ctx: commands.Context):
        summary = [
            f"Jishaku `v{package_version('jishaku')}`, discord.py `v{package_version('discord.py')}`, "
            f"`Python v{sys.version}` on `{sys.platform}`".replace("\n", ""),
            f"Bot was started <t:{self.bot.uptime.timestamp():.0f}:R>, "
            f"cog was loaded <t:{self.start_time.timestamp():.0f}:R>.",
            "",
        ]

        # detect if [procinfo] feature is installed
        if psutil:
            try:
                proc = psutil.Process()

                with proc.oneshot():
                    try:
                        mem = proc.memory_full_info()
                        summary.append(
                            f"Using `{natural_size(mem.rss)}` physical memory and "
                            f"`{natural_size(mem.vms)}` virtual memory, "
                            f"`{natural_size(mem.uss)}` of which unique to this process."
                        )
                    except psutil.AccessDenied:
                        pass

                    try:
                        name = proc.name()
                        pid = proc.pid
                        thread_count = proc.num_threads()

                        summary.append(f"Running on `PID {pid}` (`{name}`) with `{thread_count}` thread(s).")
                    except psutil.AccessDenied:
                        pass
            except psutil.AccessDenied:
                summary.append(
                    "psutil is installed, but this process does not have high enough access rights "
                    "to query process information."
                )
            finally:
                summary.append("")  # blank line

        summary += [
            f"There are `{len(self.bot.app_commands)}` application commands and "
            f"`{len(self.bot.commands)}` prefixed commands registered to this bot.",
            "",  # blank line
        ]

        cache_summary = f"`{len(self.bot.guilds)}` guild(s) and `{get_member_count(self.bot)}` user(s)"

        # Show shard settings to summary
        if isinstance(self.bot, discord.AutoShardedClient):
            if len(self.bot.shards) > 20:
                summary.append(
                    f"This bot is automatically sharded (`{len(self.bot.shards)}` shards of `{self.bot.shard_count}`)"
                    f" and can see {cache_summary}."
                )
            else:
                shard_ids = "`, `".join(str(i) for i in self.bot.shards.keys())
                summary.append(
                    f"This bot is automatically sharded (Shards `{shard_ids}` of `{self.bot.shard_count}`)"
                    f" and can see {cache_summary}."
                )
        elif self.bot.shard_count:
            summary.append(
                f"This bot is manually sharded (Shard `{self.bot.shard_id}` of `{self.bot.shard_count}`)"
                f" and can see {cache_summary}."
            )
        else:
            summary.append(f"This bot is not sharded and can see {cache_summary}.")

        # pylint: disable=protected-access
        if self.bot._connection.max_messages:
            message_cache = f"Message cache capped at `{self.bot._connection.max_messages}`"
        else:
            message_cache = "Message cache is disabled"

        if discord.version_info >= (1, 5, 0):
            presence_intent = f"presence intent is *{'enabled' if self.bot.intents.presences else 'disabled'}*"
            members_intent = f"members intent is *{'enabled' if self.bot.intents.members else 'disabled'}*"

            summary.append(f"{message_cache}, {presence_intent} and {members_intent}.")

            if discord.version_info >= (2, 0, 0):
                summary.append(
                    f"This bot *{'can' if self.bot.intents.message_content else 'cannot'}* read message content."
                )
        else:
            guild_subscriptions = (
                f"guild subscriptions are *{'enabled' if self.bot._connection.guild_subscriptions else 'disabled'}*"
            )

            summary.append(f"{message_cache} and {guild_subscriptions}.")

        # pylint: enable=protected-access

        # Show websocket latency in milliseconds
        summary.append("")  # blank line
        summary.append(f"Average websocket latency: `{round(self.bot.latency * 1000, 2)}ms`")

        await ctx.send("\n".join(summary))

    @Feature.Command(
        parent="",
        standalone_ok=True,
        name="voice",
        aliases=["vc"],
        brief="Voice-related commands",
        invoke_without_command=True,
        ignore_extra=False,
    )
    async def jsk_voice(self, ctx: commands.Context):
        """
        Voice-related commands.
        If invoked without subcommand, relays current voice state.
        """

        if await self.voice_check(ctx):
            return

        # give info about the current voice client if there is one
        voice = ctx.guild.voice_client

        if not voice or not voice.is_connected():
            return await ctx.send("Not connected.")

        await ctx.send(
            f"Connected to {voice.channel.name}, "
            f"{'paused' if voice.is_paused() else 'playing' if voice.is_playing() else 'idle'}."
        )

    @Feature.Command(
        parent="",
        standalone_ok=True,
        name="shell",
        aliases=["bash", "sh", "powershell", "ps1", "ps", "cmd"],
    )
    async def jsk_shell(self, ctx: commands.Context, *, argument: codeblock_converter):
        """
        Executes statements in the system shell.

        This uses the system shell as defined in $SHELL, or `/bin/bash` otherwise.
        Execution can be cancelled by closing the paginator.
        """

        async with ReplResponseReactor(ctx.message):
            with self.submit(ctx):
                with ShellReader(argument.content) as reader:
                    prefix = "```" + reader.highlight

                    paginator = WrappedPaginator(prefix=prefix, max_size=1975)
                    paginator.add_line(f"{reader.ps1} {argument.content}```\n```{reader.highlight}\n")

                    interface = PaginatorInterFace(ctx.bot, paginator, owner=ctx.author)
                    self.bot.loop.create_task(interface.send_to(ctx))

                    async for line in reader:
                        if interface.closed:
                            return
                        await interface.add_line(line)

                await interface.add_line(f"\n[status] Return code {reader.close_code}")

    @Feature.Command(parent="", standalone_ok=True, name="git")
    async def jsk_git(self, ctx: commands.Context, *, argument: codeblock_converter):
        """
        Shortcut for 'jsk sh git'. Invokes the system shell.
        """

        return await ctx.invoke(self.jsk_shell, argument=Codeblock(argument.language, "git " + argument.content))

    @Feature.Command(parent="", standalone_ok=True, name="pip")
    async def jsk_pip(self, ctx: commands.Context, *, argument: codeblock_converter):
        """
        Shortcut for 'jsk sh pip'. Invokes the system shell.
        """

        return await ctx.invoke(self.jsk_shell, argument=Codeblock(argument.language, "pip " + argument.content))

    @Feature.Command(parent="", standalone_ok=True, name="source", aliases=["src"])
    async def jsk_source(self, ctx: commands.Context, *, command_name: str):
        """
        Displays the source code for a command.
        """

        command: commands.Command | app_commands.Command

        if not (command := self.bot.get_command(command_name)):
            if not (command := self.bot.tree.get_command(command_name)):
                if maybe_command := self.bot.tree.get_command((split := command_name.split(" "))[0]):
                    # we got a group

                    command = maybe_command.get_command(split[1])

        if not command:
            return await ctx.send(f"Couldn't find command `{command_name}`.")

        try:
            source_lines, _ = inspect.getsourcelines(command.callback)
        except (TypeError, OSError):
            return await ctx.send(f"Was unable to retrieve the source for `{command}` for some reason.")

        source_text = "".join(source_lines)

        filename = "source.py"

        try:
            filename = pathlib.Path(inspect.getfile(command.callback)).name
        except (TypeError, OSError):
            pass

        await ctx.send(file=discord.File(filename=filename, fp=io.BytesIO(source_text.encode("utf-8"))))

    @Feature.Command(parent="", standalone_ok=True, name="cat")
    async def jsk_cat(self, ctx: commands.Context, argument: str):  # pylint: disable=too-many-locals
        """
        Read out a file, using syntax highlighting if detected.

        Lines and linespans are supported by adding '#L12' or '#L12-14' etc to the end of the filename.
        """

        match = self.__cat_line_regex.search(argument)

        if not match:  # should never happen
            return await ctx.send("Couldn't parse this input.")

        path = match.group(1)

        line_span = None

        if match.group(2):
            start = int(match.group(2))
            line_span = (start, int(match.group(3) or start))

        if not os.path.exists(path) or os.path.isdir(path):
            return await ctx.send(f"`{path}`: No file by that name.")

        size = os.path.getsize(path)

        if size <= 0:
            return await ctx.send(
                f"`{path}`: Cowardly refusing to read a file with no size stat"
                f" (it may be empty, endless or inaccessible)."
            )

        if size > 128 * (1024**2):
            return await ctx.send(f"`{path}`: Cowardly refusing to read a file >128MB.")

        def check(message: discord.Message) -> bool:
            return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id

        file_format = False
        await ctx.send("Would you like this in the form of a file rather than a paginator? `[yes|no]`")
        while True:
            try:
                msg: discord.Message = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                await ctx.send("You took too long to respond, imma take that as a no")
                break
            else:
                if msg.content.lower() == "yes":
                    file_format = True
                break

        try:
            with open(path, "rb") as file:
                if file_format and not JISHAKU_FORCE_PAGINATOR:  # File "full content" preview limit
                    if line_span:
                        content, *_ = guess_file_traits(file.read())

                        lines = content.split("\n")[line_span[0] - 1 : line_span[1]]

                        await ctx.send(
                            file=discord.File(
                                filename=pathlib.Path(file.name).name,
                                fp=io.BytesIO("\n".join(lines).encode("utf-8")),
                            )
                        )
                    else:
                        await ctx.send(file=discord.File(filename=pathlib.Path(file.name).name, fp=file))
                else:
                    paginator = WrappedFilePaginator(file, line_span=line_span, max_size=1985)
                    interface = PaginatorInterFace(ctx.bot, paginator, owner=ctx.author)
                    await interface.send_to(ctx)
        except UnicodeDecodeError:
            return await ctx.send(f"`{path}`: Couldn't determine the encoding of this file.")
        except ValueError as exc:
            return await ctx.send(f"`{path}`: Couldn't read this file, {exc}")

    @Feature.Command(parent="", standalone_ok=True, name="curl")
    async def jsk_curl(self, ctx: commands.Context, url: str):
        """
        Download and display a text file from the internet.

        This command is similar to jsk cat, but accepts a URL.
        """

        # remove embed maskers if present
        url = url.lstrip("<").rstrip(">")

        async with ReplResponseReactor(ctx.message):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.read()
                    hints = (response.content_type, url)
                    code = response.status

            if not data:
                return await ctx.send(f"HTTP response was empty (status code {code}).")

            def check(message: discord.Message) -> bool:
                return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id

            file_format = False
            await ctx.send("Would you like this in the form of a file rather than a paginator? `[yes|no]`")
            while True:
                try:
                    msg: discord.Message = await self.bot.wait_for("message", timeout=60, check=check)
                except asyncio.TimeoutError:
                    await ctx.send("You took too long to respond, imma take that as a no")
                    break
                else:
                    if msg.content.lower() == "yes":
                        file_format = True
                    break

            if file_format and not JISHAKU_FORCE_PAGINATOR:  # File "full content" preview limit
                # Shallow language detection
                language = None

                for hint in hints:
                    language = get_language(hint)

                    if language:
                        break

                await ctx.send(file=discord.File(filename=f"response.{language or 'txt'}", fp=io.BytesIO(data)))
            else:
                try:
                    paginator = WrappedFilePaginator(io.BytesIO(data), language_hints=hints, max_size=1985)
                except UnicodeDecodeError:
                    return await ctx.send(f"Couldn't determine the encoding of the response. (status code {code})")
                except ValueError as exc:
                    return await ctx.send(f"Couldn't read response (status code {code}), {exc}")

                interface = PaginatorInterFace(ctx.bot, paginator, owner=ctx.author)
                await interface.send_to(ctx)

    @Feature.Command(parent="", standalone_ok=True, name="dis", aliases=["disassemble"])
    async def jsk_disassemble(self, ctx: commands.Context, *, argument: codeblock_converter):
        """
        Disassemble Python code into bytecode.
        """

        arg_dict = get_var_dict_from_ctx(ctx, SCOPE_PREFIX)

        async with ReplResponseReactor(ctx.message):
            text = "\n".join(disassemble(argument.content, arg_dict=arg_dict))

            def check(message: discord.Message) -> bool:
                return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id

            file_format = False
            await ctx.send("Would you like this in the form of a file rather than a paginator? `[yes|no]`")
            while True:
                try:
                    msg: discord.Message = await self.bot.wait_for("message", timeout=60, check=check)
                except asyncio.TimeoutError:
                    await ctx.send("You took too long to respond, imma take that as a no")
                    break
                else:
                    if msg.content.lower() == "yes":
                        file_format = True
                    break

            if file_format and not JISHAKU_FORCE_PAGINATOR:  # File "full content" preview limit
                await ctx.send(file=discord.File(filename="dis.py", fp=io.BytesIO(text.encode("utf-8"))))
            else:
                paginator = WrappedPaginator(prefix="```py", max_size=1985)

                paginator.add_line(text)

                interface = PaginatorInterFace(ctx.bot, paginator, owner=ctx.author)
                await interface.send_to(ctx)

    @Feature.Command(parent="", standalone_ok=True, name="py", aliases=["python"])
    async def jsk_python(self, ctx: commands.Context, *, argument: codeblock_converter):
        """
        Direct evaluation of Python code.
        """

        def check(message: discord.Message) -> bool:
            return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id

        arg_dict = get_var_dict_from_ctx(ctx, SCOPE_PREFIX)
        arg_dict["_"] = self.last_result

        scope = self.scope

        try:
            async with ReplResponseReactor(ctx.message):
                with self.submit(ctx):
                    executor = AsyncCodeExecutor(argument.content, scope, arg_dict=arg_dict)
                    async for send, result in AsyncSender(executor):
                        if result is None:
                            continue

                        self.last_result = result

                        if isinstance(result, discord.File):
                            send(await ctx.send(file=result))
                        elif isinstance(result, discord.Embed):
                            send(await ctx.send(embed=result))
                        elif isinstance(result, PaginatorInterFace):
                            send(await result.send_to(ctx))
                        else:
                            if not isinstance(result, str):
                                # repr all non-strings
                                result = repr(result)

                            if len(result) <= 2000:
                                if result.strip() == "":
                                    result = "\u200b"

                                send(await ctx.send(result.replace(self.bot.http.token, "[TOKEN]")))

                            else:
                                ye_or_nu = "no"
                                send(
                                    await ctx.send(
                                        "The output text is longer than my ~~`pp`~~**message cap**, would you like it in a file format rather than a paginator? `[yes|no]`"
                                    )
                                )
                                while True:
                                    try:
                                        msg: discord.Message = await self.bot.wait_for(
                                            "message", timeout=60, check=check
                                        )
                                    except asyncio.TimeoutError:
                                        send(await ctx.send("You took too long to respond, I'll take that as a no :|"))
                                        ye_or_nu = "no"
                                        break
                                    else:
                                        if msg.content.lower() == "yes":
                                            ye_or_nu = "yes"
                                        break

                                if ye_or_nu == "yes" and not JISHAKU_FORCE_PAGINATOR:
                                    send(
                                        await ctx.send(
                                            file=discord.File(
                                                filename="output.py",
                                                fp=io.BytesIO(result.encode("utf-8")),
                                            )
                                        )
                                    )

                                else:
                                    paginator = WrappedPaginator(prefix="```py", suffix="```", max_size=1985)

                                    try:
                                        paginator.add_line(result)
                                    except ValueError:
                                        paginator.add_line(
                                            "NOTE: Your output text is too big for the paginator! Therefore, we only included the first 2000 chars or so"
                                        )
                                        paginator.add_line(result[:1975])

                                    interface = PaginatorInterFace(ctx.bot, paginator, owner=ctx.author)
                                    send(await interface.send_to(ctx))

        finally:
            scope.clear_intersection(arg_dict)

    @Feature.Command(
        parent="",
        standalone_ok=True,
        name="py_inspect",
        aliases=["pyi", "python_inspect", "pythoninspect"],
    )
    async def jsk_python_inspect(
        self, ctx: commands.Context, *, argument: codeblock_converter
    ):  # pylint: disable=too-many-locals
        """
        Evaluation of Python code with inspect information.
        """

        arg_dict = get_var_dict_from_ctx(ctx, SCOPE_PREFIX)
        arg_dict["_"] = self.last_result

        scope = self.scope

        try:
            async with ReplResponseReactor(ctx.message):
                with self.submit(ctx):
                    executor = AsyncCodeExecutor(argument.content, scope, arg_dict=arg_dict)
                    async for send, result in AsyncSender(executor):
                        self.last_result = result

                        header = repr(result).replace("``", "`\u200b`").replace(self.bot.http.token, "[TOKEN]")

                        if len(header) > 485:
                            header = header[0:482] + "..."

                        lines = [f"=== {header} ===", ""]

                        for name, res in all_inspections(result):
                            lines.append(f"{name:16.16} :: {res}")

                        text = "\n".join(lines)

                        if (
                            len(text) < 50_000 and not ctx.author.is_on_mobile() and not JISHAKU_FORCE_PAGINATOR
                        ):  # File "full content" preview limit
                            send(
                                await ctx.send(
                                    file=discord.File(
                                        filename="inspection.prolog",
                                        fp=io.BytesIO(text.encode("utf-8")),
                                    )
                                )
                            )
                        else:
                            paginator = WrappedPaginator(prefix="```prolog", max_size=1985)

                            paginator.add_line(text)

                            interface = PaginatorInterFace(ctx.bot, paginator, owner=ctx.author)
                            send(await interface.send_to(ctx))
        finally:
            scope.clear_intersection(arg_dict)

    @Feature.Command(parent="", standalone_ok=True, name="tasks")
    async def jsk_tasks(self, ctx: commands.Context):
        """
        Shows the currently running jishaku tasks.
        """

        if not self.tasks:
            return await ctx.send("No currently running tasks.")

        paginator = commands.Paginator(max_size=1985)

        for task in self.tasks:
            paginator.add_line(
                f"{task.index}: `{task.ctx.command.qualified_name}`, invoked at "
                f"{task.ctx.message.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )

        interface = PaginatorInterFace(ctx.bot, paginator, owner=ctx.author)
        return await interface.send_to(ctx)


async def setup(bot: commands.Bot):
    """
    The setup function defining the jishaku.cog and jishaku extensions.
    """

    await bot.add_cog(Jishaku(bot=bot))
