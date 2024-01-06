import ast
import asyncio
import inspect
import io
import os
import random
import re
import textwrap
import time
import traceback
import types
from contextlib import redirect_stdout
from typing import Any, Dict, List, Literal, Optional

import aiohttp
import discord
from discord.ext import commands
from helper_bot import NotGDKID

from utils import BotEmojis, CHOICES, Embed, NewEmote

quote = r'"'
wraps = r"\(\)\[\]\{\}"
expression = rf"[\w\./\\:=<>!{wraps}{quote}', ]"

# fmt: off
REGEX_LIST: list[re.Pattern[str]] = [
    re.compile(rf"^(?:async\s+)?def\s+\w+\({expression}*\)(?::|\s*->\s*[\w\[\]\(\),\s]+:)\s*$"),  # FUNCTION
    re.compile(r"^class\s+\w+(?:\(.*\))?:"),                                                      # CLASS
    re.compile(rf"^if\s+{expression}+:\s*$"),                                                     # IF
    re.compile(rf"^elif\s+{expression}+:\s*$"),                                                   # ELIF
    re.compile(r"^else:\s*$"),                                                                    # ELSE
    re.compile(r"^try:\s*$"),                                                                     # TRY
    re.compile(r"^except(?:\s+(?:\(?(?:[\w\.]*)(?:,\s+?)?\)?(?:|\s+as\s+\w+))|\s+\w)?:\s*$"),     # EXCEPT
    re.compile(r"^finally:\s*$"),                                                                 # FINALLY
    re.compile(rf"^(?:async\s+)?with\s+[\w\.]+\({expression}*\)(?:\s+as\s+\w+)?:\s*$"),           # WITH
    re.compile(rf"^(?:async\s+)?for\s+\w+\s+in\s+{expression}+:\s*$"),                            # FOR
    re.compile(rf"^while\s+{expression}+:\s*$"),                                                  # WHILE
    re.compile(r"{\s*$"),                                                                         # DICT
    re.compile(r"\[\s*$"),                                                                        # LIST
    re.compile(r"\(\s*$"),                                                                        # TUPLE
    re.compile(r",\s*$"),                                                                         # BREAKLINE
    re.compile(r"^\)(?::|\s*-> [\w\[\]\(\),\s]*:)\s*$"),                                          # MULTILINE FUNCTION DECLARATION
]


class SuppressTraceback(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        self.owner = ctx.author
        self.delete_me = False
        super().__init__(timeout=45)

    async def interaction_check(self, interaction: discord.Interaction):
        """Check that determines whether this interaction should be honored"""
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message(
                content=random.choice(CHOICES), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()

    @discord.ui.button(
        label="Suppress",
        style=discord.ButtonStyle.danger,
        emoji=NewEmote.from_name(BotEmojis.GDX),
    )
    async def close_menu(self, *_):
        self.delete_me = True
        self.stop()


class SQLTable:
    def __init__(self) -> None:
        self._columns: Dict[str, List[str]] = {}
        self._widths: List[int] = []

    def add_columns(self, names: List[str]) -> None:
        for name in names:
            self._columns[name] = []
            self._widths.append(len(name) + 2)

    def add_rows(self, rows: List[List[Any]]) -> None:
        for row in rows:
            for idx, column in enumerate(self._columns.values()):
                column.append(str(row[idx]))

    def even_out(self) -> None:
        self._widths = [
            len(max(i + [n], key=lambda k: len(k))) for n, i in self._columns.items()
        ]
        self._columns = {
            f" {tu[0]:<{self._widths[idx]}} ": [f" {i:<{self._widths[idx]}} " for i in tu[1]]
            for idx, tu in enumerate(self._columns.items())
        }

    def build(self) -> str:
        LINE = f"+{'+'.join('-' * (w + 2) for w in self._widths)}+"
        COLUMN_NAMES = f"|{'|'.join(list(self._columns.keys()))}|"
        final = [LINE, COLUMN_NAMES, LINE]
        for i in range(len((li := list(self._columns.values()))[0])):
            final.append(f"|{'|'.join([li[col][i] for col in range(len(li))])}|")
        final.append(LINE)

        return "\n".join(final)


# fmt: on
class Eval(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client
        self.emoji = ""

    @staticmethod
    def async_compile(source: str, filename: str, mode: Literal["eval", "exec"]):
        return compile(source, filename, mode, flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, optimize=0)

    @staticmethod
    async def maybe_await(coro: Any):
        for _ in range(2):
            if inspect.isawaitable(coro):
                coro = await coro
            else:
                return coro
        return coro

    @staticmethod
    def simulate_repl(src_text: str) -> str:
        """
        Does things
        """

        src_lines: list[str] = src_text.split("\n")
        repl_lines: list[str] = []
        in_indent = False
        prefix = ">>>"

        for index, line in enumerate(src_lines):
            prefix = ">>>"
            if not in_indent:
                for pattern in REGEX_LIST:
                    if pattern.search(line) is not None:
                        in_indent = True
                        break

            if in_indent and re.search(r"^[ ]*$", line) is not None or in_indent and line.startswith(" "):
                prefix = "..."

            if prefix == "..." and re.search(r"^[ ]*$", src_lines[index - 1]) is not None:
                prefix = ">>>"

            if re.search(r"^[ ]*$", line) is not None and prefix == "...":
                repl_lines.append(f"{prefix} {line}")
                continue

            if re.search(r"^[ ]*$", line) is not None:
                prefix = ">>>"
                in_indent = False

            if re.search(r"^(?:\)|}|]) *$", line) is not None:
                prefix = "..."

            repl_lines.append(f"{prefix} {line}")

        return "\n".join(repl_lines)

    @staticmethod
    def cleanup_code(content: str):
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```") and content.count("\n") > 0:
            return "\n".join(content.split("\n")[1:-1])
        # remove `foo`
        return content.strip("` \n")

    @staticmethod
    def pretty_query(query: str):
        start = "postgres=# "
        lines = query.split("\n")

        lines[0] = start + lines[0]
        lines = [lines[0]] + [len(start) * " " + line for line in lines[1:]]

        return "\n".join(lines)

    @staticmethod
    def paginate(text: str, max_text: int = 1990) -> list:
        """One that's less weird"""
        if type(text) != str:
            text = str(text)
        if len(text) <= max_text:
            return [text]
        pages = []
        while len(text) != 0:
            pages.append(text[:max_text])
            text = text[max_text:]
        return pages

    def get_environment(self, ctx: commands.Context) -> dict:
        env = {
            "asyncio": asyncio,
            "aiohttp": aiohttp,
            "discord": discord,
            "commands": commands,
            "ctx": ctx,
            "client": self.client,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "os": os,
            "re": re,
            "random": random,
            "guilds": len(self.client.guilds),
            "description": self.client.description,
            "self": self,
            "getsource": inspect.getsource,
            self.client.__class__.__name__: self.client,
        }

        env.update(globals())

        env["env"] = env

        return env

    @commands.command(
        name="sql",
        aliases=["query"],
        brief="Run some SQL",
        hidden=True,
    )
    @commands.is_owner()
    async def sql(self, ctx: commands.Context, *, query: str):
        if not hasattr(self.client, "db"):
            return await ctx.reply("you dont have a db connected lol")

        query = self.cleanup_code(query)

        gamer_strats = self.client.db.execute if query.count(";") >= 1 else self.client.db.fetch

        try:
            start = time.monotonic()
            results = await gamer_strats(query)
            exec_time = round((time.monotonic() - start) * 1000, 2)
            row_count = len(results)
        except Exception:
            return await ctx.send(f"```py\n{traceback.format_exc()}\n```")

        if isinstance(results, str) or not results:
            return await ctx.send(f"```\n{self.pretty_query(query)}\n\n{results}\n\nquery completed in {exec_time}ms\n```")

        table = SQLTable()

        table.add_columns(list(results[0].keys()))
        table.add_rows([list(r.values()) for r in results])
        table.even_out()

        table = table.build()

        s = "s" if row_count != 1 else ""
        msg = f"{self.pretty_query(query)}\n\n{table}\n({row_count} row{s})\n\nfinished in {exec_time}ms"
        if len(msg) > 2000:
            fp = io.BytesIO(msg.encode("utf-8"))
            file = discord.File(fp, "thiccc.txt")
            await ctx.send("the result was too thiccc, so i yeeted it into a file", file=file)
        else:
            await ctx.send(f"```\n{msg}\n```")

    @commands.command(
        name="debug",
        aliases=["dbg"],
        brief="Evaluate a line of python code",
        hidden=True,
    )
    @commands.is_owner()
    async def debug(self, ctx: commands.Context, *, code: str):
        env = self.get_environment(ctx)

        code = self.cleanup_code(code)
        try:
            compiled = self.async_compile(code, "<debug>", "eval")
            result = eval(compiled, env)
        except Exception as e:
            stuff = traceback.format_exc()
            view = SuppressTraceback(ctx=ctx)
            embed = Embed(title="FUCK!", description=f"```py\n{stuff}```", color=0x2E3135)
            message = await ctx.reply(embed=embed, mention_author=True, view=view)

            await view.wait()
            if view.delete_me:
                await message.delete()

            else:
                await message.edit(view=None)

            return
        paginated_result: list[str] = self.paginate(result)
        list_of_embeds: list[Embed] = []
        for page in paginated_result:
            if page == paginated_result[-1]:
                embed = Embed(
                    description=f"```py\n{page}\n```",
                    color=0x2E3135,
                )
                list_of_embeds.append(embed)
                break
            embed = Embed(description=f"```py\n{page}\n```", color=0x2E3135)
            list_of_embeds.append(embed)
            if len(list_of_embeds) == 3:
                if len(paginated_result) == 3:
                    break
                await ctx.send(embeds=list_of_embeds)
                list_of_embeds.clear()
                continue
            elif len(list_of_embeds) != len(paginated_result):
                continue
            else:
                break
        await ctx.send(embeds=[embed for embed in list_of_embeds])
        await ctx.message.add_reaction(BotEmojis.YES)

    @commands.group(
        invoke_without_command=True,
        name="repl",
        brief="Open a REPL session in Discord",
        hidden=True,
    )
    @commands.is_owner()
    async def repl(self, ctx: commands.Context, *, code: Optional[str] = None):
        if code:
            code = self.cleanup_code(code)
            output = self.simulate_repl(code)
            await ctx.send(f"```py\n{output}\n```")
            return

        start_phrases: list[str] = [
            "Remember to close the session when you're done",
            "If you're doing this in public, try not to shit yourself",
            "Btw coding knowledge is needed for this command. I doubt you but go ahead",
            "Good luck!",
            "Don't mess up",
            "Available commands: `cya`",
            "Also I clogged the toilet :P",
            "Do you even know how to use this tbh; `cya` to exit",
            "New features when?",
            "You should go outside more",
            "Probably shouldn't've eaten that whole cake in one sitting yeah?",
            "How can I help you today",
            "Don't panic",
            "Keep calm",
            "Focus now.",
            "Working on somethin new, or f*ckin around like usual?",
            "~~I got your account banned from Hypixel~~ *WAIT*",
            "Give me code to run",
            "Type to type",
            "1 + 1 is 2, if you didn't know",
            "Don't expose yourself",
            "Wake up",
            "Thats a fact",
            "No denying that",
        ]

        closing_phrases: list[str] = [
            "Goodbye",
            "Cya",
            "Closing the session that you closed",
            "Farewell",
            "Bye",
            "Don't come back",
            "Exited the REPL",
            "Closed session",
            "Carry on",
            ":)",
            "I'm free!",
        ]

        env = self.get_environment(ctx)
        env["__builtins__"] = __builtins__
        await ctx.send(f"REPL started. {random.choice(start_phrases)}")

        while True:
            try:
                response = await self.client.wait_for(
                    "message",
                    timeout=600,
                    check=lambda m: str(m.content).startswith(f"`") and m.author == ctx.author,
                )

                cleaned = self.cleanup_code(response.content)

                if cleaned in ("cya", "exit()"):
                    await ctx.send(random.choice(closing_phrases))
                    return

                executor = None
                if cleaned.count("\n") == 0:
                    try:
                        code = self.async_compile(cleaned, "<repl session>", "eval")
                    except SyntaxError:
                        pass
                    else:
                        executor = eval

                if executor is None:
                    try:
                        code = self.async_compile(cleaned, "<repl session>", "exec")
                    except SyntaxError as e:
                        embed = Embed(
                            title="FUCK!",
                            description=f"```py\n{traceback.format_exc()}```",
                            color=0x2E3135,
                        )
                        await ctx.send(embed=embed)
                        continue

                env["message"] = response
                stdout = io.StringIO()

                msg = ""

                try:
                    assert code
                    with redirect_stdout(stdout):
                        if executor is None:
                            result = types.FunctionType(code, env)()
                        else:
                            result = executor(code, env)
                        result = await self.maybe_await(result)
                except:
                    value = stdout.getvalue()
                    msg = "{}{}".format(value, traceback.format_exc())
                else:
                    value = stdout.getvalue()
                    if result is not None:
                        msg = "{}{}".format(value, result)
                    elif result is None:
                        try:
                            with redirect_stdout(stdout):
                                result = await self.maybe_await(eval(cleaned.split("\n")[-1], env))

                                if result is None:
                                    raise
                        except:
                            msg = "{}".format(value)
                        else:
                            msg = "{}{}".format(value, result)

                __input = self.simulate_repl(cleaned)

                embed = Embed(description=f"```py\n{__input}\n\n{msg}```", color=0x2E3135)

                try:
                    if len(msg) > 1000:
                        list_of_embeds: list[Embed] = []
                        paginated_text: list[str] = self.paginate(msg, max_text=1000)
                        first_embed = Embed(
                            description=f"```py\n{__input}\n\n{paginated_text[0]}```",
                            colour=0x2E3135,
                        )
                        paginated_text.pop(0)
                        await ctx.send(embed=first_embed)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                embed = Embed(
                                    description=f"```py\n{page}\n```",
                                    color=0x2E3135,
                                )
                                list_of_embeds.append(embed)
                                break
                            embed = Embed(description=f"```py\n{page}\n```", color=0x2E3135)
                            list_of_embeds.append(embed)
                            if len(list_of_embeds) == 3:
                                if len(paginated_text) == 3:
                                    break
                                await ctx.send(embeds=list_of_embeds)
                                list_of_embeds.clear()
                                continue
                            elif len(list_of_embeds) != len(paginated_text):
                                continue
                            else:
                                break
                        await ctx.send(embeds=list_of_embeds)
                    else:
                        await ctx.send(embed=embed)
                except discord.Forbidden:
                    pass
                except discord.HTTPException as e:
                    await ctx.send("unexpected error: `{}`".format(e))

            except asyncio.TimeoutError:
                await ctx.reply(
                    content="bro you're supposed to end these sessions once you're done wipe your own ass for once"
                )
                return

    @commands.command(name="eval", aliases=["exec"], brief="Runs code", hidden=True)
    @commands.is_owner()
    async def _eval(self, ctx: commands.Context, *, code: str):
        env = self.get_environment(ctx)

        env.update(globals())

        code = self.cleanup_code(code)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(code, "    ")}'

        color = 0x2E3135

        try:
            exec(to_compile, env)
        except Exception as e:
            embed = Embed(
                title="FUCK!",
                description=f"```py\n{e.__class__.__name__}: {e}\n```",
                color=color,
            )
            await ctx.send(embed=embed)

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            embed = Embed(
                title="FUCK!",
                description=f"```py\n{value}{traceback.format_exc()}\n```",
                color=color,
            )
            await ctx.send(embed=embed)
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        embed = Embed(description=f"```py\n{value}\n```", color=color)
                        await ctx.send(embed=embed)
                    except:
                        paginated_text = Eval.paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                embed = Embed(description=f"```py\n{page}\n```", color=color)
                                await ctx.send(embed=embed)
                                break
                            embed = Embed(description=f"```py\n{page}\n```", color=color)
                            await ctx.send(embed=embed)
            else:
                try:
                    embed = Embed(description=f"```py\n{value}{ret}\n```", color=color)
                    await ctx.send(embed=embed)
                except:
                    paginated_text = Eval.paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            embed = Embed(description=f"```py\n{page}\n```", color=color)
                            await ctx.send(embed=embed)
                            break
                        embed = Embed(description=f"```py\n{page}\n```", color=color)
                        await ctx.send(embed=embed)

            await ctx.message.add_reaction(BotEmojis.YES)

    @repl.command(name="exec", aliases=["run"], brief="Runs code", hidden=True)
    @commands.is_owner()
    async def _exec(self, ctx: commands.Context, *, code: str):
        cleaned = self.cleanup_code(code)

        executor = None
        if cleaned.count("\n") == 0:
            try:
                code = self.async_compile(cleaned, "<repl eval>", "eval")
            except SyntaxError:
                pass
            else:
                executor = eval

        if executor is None:
            try:
                code = self.async_compile(cleaned, "<repl exec>", "exec")
            except SyntaxError as e:
                embed = Embed(
                    title="FUCK!",
                    description=f"```py\n{traceback.format_exc()}```",
                    color=0x2E3135,
                )
                view = SuppressTraceback(ctx=ctx)
                error_msg: discord.Message = await ctx.send(embed=embed, view=view)

                await view.wait()
                if view.delete_me:
                    await error_msg.delete()

                else:
                    await error_msg.edit(view=None)
                return

        env = self.get_environment(ctx)
        env["__builtins__"] = __builtins__
        stdout = io.StringIO()

        msg = ""

        try:
            with redirect_stdout(stdout):
                if executor is None:
                    result = types.FunctionType(code, env)()  # type: ignore
                else:
                    result = executor(code, env)
                result = await self.maybe_await(result)
        except:
            value = stdout.getvalue()
            msg = "{}{}".format(value, traceback.format_exc())
        else:
            value = stdout.getvalue()
            if result is not None:
                msg = "{}{}".format(value, result)
            elif result is None:
                try:
                    with redirect_stdout(stdout):
                        result = await self.maybe_await(eval(cleaned.split("\n")[-1], env))

                        if result is None:
                            raise
                except:
                    msg = "{}".format(value)
                else:
                    msg = "{}{}".format(value, result)

        __input = self.simulate_repl(cleaned)

        embed = Embed(description=f"```py\n{__input}\n\n{msg}```", color=0x2E3135)

        try:
            if len(msg) > 1000:
                list_of_embeds: list[Embed] = []
                paginated_text: list[str] = self.paginate(msg, max_text=1000)
                first_embed = Embed(
                    description=f"```py\n{__input}\n\n{paginated_text[0]}```",
                    colour=0x2E3135,
                )
                paginated_text.pop(0)
                await ctx.send(embed=first_embed)
                for page in paginated_text:
                    if page == paginated_text[-1]:
                        embed = Embed(
                            description=f"```py\n{page}\n```",
                            color=0x2E3135,
                        )
                        list_of_embeds.append(embed)
                        break
                    embed = Embed(description=f"```py\n{page}\n```", color=0x2E3135)
                    list_of_embeds.append(embed)
                    if len(list_of_embeds) == 3:
                        if len(paginated_text) == 3:
                            break
                        await ctx.send(embeds=list_of_embeds)
                        list_of_embeds.clear()
                        continue
                    elif len(list_of_embeds) != len(paginated_text):
                        continue
                    else:
                        break
                await ctx.send(embeds=list_of_embeds)
            else:
                await ctx.send(embed=embed)
        except discord.Forbidden:
            pass
        except discord.HTTPException as e:
            await ctx.send("unexpected error: `{}`".format(e))


async def setup(client: NotGDKID):
    await client.add_cog(Eval(client=client))
