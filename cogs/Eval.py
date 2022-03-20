import ast
import asyncio
import inspect
import io
import os
import random
import re
import textwrap
import traceback
import types
from contextlib import redirect_stdout
from typing import *

import aiohttp
import discord
from discord.ext import commands

from config.utils import *

quote = r'"'
wraps = r"\(\)\[\]\{\}"
expression = rf"[\w\./\\:=<>!{wraps}{quote}', ]"

REGEX_LIST: list[re.Pattern[str]] = [
    re.compile(rf"^(?:async )?def \w+\({expression}*\)(?::| *-> [\w\[\]\(\), ]*:) *$"),  # FUNCTION
    re.compile(r"^class \w+(?:\(.*\))?:"),  # CLASS
    re.compile(rf"^if {expression}+: *$"),  # IF
    re.compile(rf"^elif {expression}+: *$"),  # ELIF
    re.compile(r"^else: *$"),  # ELSE
    re.compile(r"^try: *$"),  # TRY
    re.compile(r"^except(?: (?:\(?(?:[\w\.]*)(?:, ?)?\)?(?:| as \w+))| \w)?: *$"),  # EXCEPT
    re.compile(r"^finally: *$"),  # FINALLY
    re.compile(rf"^(?:async )?with [\w\.]+\({expression}*\)(?: as \w+)?: *$"),  # WITH
    re.compile(rf"^(?:async )?for \w+ in {expression}+: *$"),  # FOR
    re.compile(rf"^while {expression}+: *$"),  # WHILE
    re.compile(r"{ *$"),  # DICT
    re.compile(r"\[ *$"),  # LIST
    re.compile(r"\( *$"),  # TUPLE
    re.compile(r", *$"),  # BREAKLINE
    re.compile(r"^\)(?::| *-> [\w\[\]\(\), ]*:) *$"),  # MULTILINE FUNCTION HEADER
]


class SuppressTraceback(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        self.timeout = 45
        self.owner = ctx.author
        self.delete_me = False
        super().__init__(timeout=self.timeout)

    async def interaction_check(self, interaction: discord.Interaction):
        """Check that determines whether this interaction should be honored"""
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()

    @discord.ui.button(
        label="Suppress",
        style=discord.ButtonStyle.danger,
        emoji=NewEmote.from_name("<:x_:822656892538191872>"),
    )
    async def close_menu(self, button: discord.Button, interaction: discord.Interaction):
        self.delete_me = True
        self.stop()


class Eval(BattlerCog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.emoji = ""

    @BattlerCog.listener()
    async def on_ready(self):
        print("Eval cog loaded")

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
        index = -1
        in_indent = False
        prefix = ">>>"

        for line in src_lines:
            index += 1

            prefix = ">>>"

            if not in_indent:
                for pattern in REGEX_LIST:
                    match = pattern.search(line)
                    if match is not None:
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
        }

        env.update(globals())

        env["env"] = env

        return env

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
            stuff = "".join(traceback.format_exception(e, e, e.__traceback__))
            view = SuppressTraceback(ctx=ctx)
            embed = discord.Embed(title="FUCK!", description=f"```py\n{stuff}```", color=0x2E3135)
            embed.description = embed.description.replace(self.client.token, "[TOKEN]")
            message = await ctx.reply(embed=embed, mention_author=True, view=view)

            await view.wait()
            if view.delete_me:
                await message.delete()

            else:
                await message.edit(view=None)

            return
        paginated_result: list[str] = self.paginate(result)
        list_of_embeds: list[discord.Embed] = []
        for page in paginated_result:
            if page == paginated_result[-1]:
                embed = discord.Embed(
                    description=f"```py\n{page}\n```",
                    color=0x2E3135,
                )
                embed.description = embed.description.replace(self.client.token, "[TOKEN]")
                list_of_embeds.append(embed)
                break
            embed = discord.Embed(description=f"```py\n{page}\n```", color=0x2E3135)
            embed.description = embed.description.replace(self.client.token, "[TOKEN]")
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
        await ctx.message.add_reaction(self.client.yes)

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
                        embed = discord.Embed(
                            title="FUCK!",
                            description=f"```py\n{''.join(traceback.format_exception(e, e, e.__traceback__))}```",
                            color=0x2E3135,
                        )
                        await ctx.send(embed=embed)
                        continue

                env["message"] = response
                stdout = io.StringIO()

                msg = ""

                try:
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

                msg = msg.replace(self.client.token, "[TOKEN]")

                __input = self.simulate_repl(cleaned)

                embed = discord.Embed(description=f"```py\n{__input}\n\n{msg}```", color=0x2E3135)

                try:
                    if len(msg) > 1000:
                        list_of_embeds: list[discord.Embed] = []
                        paginated_text: list[str] = self.paginate(msg, max_text=1000)
                        first_embed = discord.Embed(
                            description=f"```py\n{__input}\n\n{paginated_text[0]}```",
                            colour=0x2E3135,
                        )
                        paginated_text.pop(0)
                        await ctx.send(embed=first_embed)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                embed = discord.Embed(
                                    description=f"```py\n{page}\n```",
                                    color=0x2E3135,
                                )
                                embed.description = embed.description.replace(self.client.token, "[TOKEN]")
                                list_of_embeds.append(embed)
                                break
                            embed = discord.Embed(description=f"```py\n{page}\n```", color=0x2E3135)
                            embed.description = embed.description.replace(self.client.token, "[TOKEN]")
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
                    await ctx.send("Unexpected error: `{}`").format(e)

            except asyncio.TimeoutError:
                await ctx.reply(
                    content="Bro you're supposed to end these sessions once you're done wipe your own ass for once"
                )
                return

    @repl.command(name="noreturn", aliases=["nr"], brief="Runs code", hidden=True)
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
            embed = discord.Embed(title="Error", description=f"```py\n{e.__class__.__name__}: {e}\n```", color=color)
            await ctx.send(embed=embed)

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            embed = discord.Embed(
                title="Error", description=f"```py\n{value}{traceback.format_exc()}\n```", color=color
            )
            await ctx.send(embed=embed)
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        embed = discord.Embed(description=f"```py\n{value}\n```", color=color)
                        await ctx.send(embed=embed)
                    except:
                        paginated_text = Eval.paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                embed = discord.Embed(description=f"```py\n{page}\n```", color=color)
                                await ctx.send(embed=embed)
                                break
                            embed = discord.Embed(description=f"```py\n{page}\n```", color=color)
                            await ctx.send(embed=embed)
            else:
                try:
                    embed = discord.Embed(description=f"```py\n{value}{ret}\n```", color=color)
                    await ctx.send(embed=embed)
                except:
                    paginated_text = Eval.paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            embed = discord.Embed(description=f"```py\n{page}\n```", color=color)
                            await ctx.send(embed=embed)
                            break
                        embed = discord.Embed(description=f"```py\n{page}\n```", color=color)
                        await ctx.send(embed=embed)

            await ctx.message.add_reaction(self.client.yes)

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
                embed = discord.Embed(
                    title="FUCK!",
                    description=f"```py\n{''.join(traceback.format_exception(e, e, e.__traceback__))}```",
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

        msg = msg.replace(self.client.token, "[TOKEN]")

        __input = self.simulate_repl(cleaned)

        embed = discord.Embed(description=f"```py\n{__input}\n\n{msg}```", color=0x2E3135)

        try:
            if len(msg) > 1000:
                list_of_embeds: list[discord.Embed] = []
                paginated_text: list[str] = self.paginate(msg, max_text=1000)
                first_embed = discord.Embed(
                    description=f"```py\n{__input}\n\n{paginated_text[0]}```",
                    colour=0x2E3135,
                )
                paginated_text.pop(0)
                await ctx.send(embed=first_embed)
                for page in paginated_text:
                    if page == paginated_text[-1]:
                        embed = discord.Embed(
                            description=f"```py\n{page}\n```",
                            color=0x2E3135,
                        )
                        embed.description = embed.description.replace(self.client.token, "[TOKEN]")
                        list_of_embeds.append(embed)
                        break
                    embed = discord.Embed(description=f"```py\n{page}\n```", color=0x2E3135)
                    embed.description = embed.description.replace(self.client.token, "[TOKEN]")
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
            await ctx.send("Unexpected error: `{}`").format(e)


def setup(client: commands.Bot):
    client.add_cog(Eval(client=client))
