import ast
import asyncio
import contextlib
import inspect
import io
import logging
import os
import sys
import threading
import traceback
from pathlib import Path
from types import FunctionType

import aiohttp
import discord
from discord.ext import commands
from discord.ui import InputText, Modal, View, button
from jishaku.paginators import WrappedPaginator
from jishaku.shim.paginator_200 import \
    PaginatorInterface as OGPaginatorInterface

from config.json import Json
from config.utils import Botcolours

logging.basicConfig(level=logging.INFO)
secrets: dict[str, str] = Json.read_json("secrets")

PLACEHOLDER = "Enter Something..."


class PaginatorInterface(OGPaginatorInterface):
    def update_view(self):
        self.button_start.label = "❮❮❮"
        self.button_start.emoji = None
        self.button_previous.label = "❮"
        self.button_previous.emoji = None
        self.button_current.label = f"{self.display_page + 1} / {self.page_count}"
        self.button_current.disabled = True
        self.button_next.emoji = None
        self.button_next.label = "❯"
        self.button_last.emoji = None
        self.button_last.label = "❯❯❯"

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

    @property
    def send_kwargs(self):
        return {"content": self.pages[self.display_page], "view": self}

    async def send_to(self, interaction: discord.Interaction):
        self.remove_item(self.children[5])
        self.update_view()
        stop_after_send = False

        if self.page_count == 1:
            stop_after_send = True

        self.message: discord.Interaction = await interaction.response.send_message(**self.send_kwargs, ephemeral=True)

        if stop_after_send:
            self.stop()
            if self.task:
                self.task.cancel()

            return

        self.send_lock.set()

        if self.task:
            self.task.cancel()

        self.task = self.bot.loop.create_task(self.wait_loop())

    async def wait_loop(self):
        """
        Waits on a loop for updates to the interface. This should not be called manually - it is handled by `send_to`.
        """

        discord.Interaction.delete_original_message
        try:
            while not self.bot.is_closed():
                await asyncio.wait_for(self.send_lock_delayed(), timeout=self.timeout)

                self.update_view()

                try:
                    await self.message.edit_original_message(**self.send_kwargs)
                except discord.NotFound:
                    # something terrible has happened
                    return
        except (asyncio.CancelledError, asyncio.TimeoutError) as exception:
            self.close_exception = exception

            if self.bot.is_closed():
                # Can't do anything about the messages, so just close out to avoid noisy error
                return

            # If the message was already deleted, this part is unnecessary
            if not self.message:
                return

            await self.message.edit_original_message(view=None)

    async def interaction_check(self, interaction: discord.Interaction):
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()
        await self.message.edit_original_message(view=None)
        return


class RickrollBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = False

        super().__init__(command_prefix=".", help_command=None, intents=intents)

    async def close(self, restart: bool = False):
        for child in self.persistent_views[0].children:
            child.disabled = True

        e = self.control_msg.embeds[0].copy()
        e.colour = Botcolours.red

        await self.control_msg.edit(embed=e, view=self.persistent_views[0])

        if restart is True:
            for voice in self.voice_clients:
                try:
                    await voice.disconnect()

                except Exception:
                    continue

            if self.ws is not None and self.ws.open:
                await self.ws.close(code=1000)

            sys.exit(69)

        else:
            await super().close()

    async def on_ready(self):
        self.g: discord.Guild = self.get_guild(831692952027791431)
        self.r: discord.Role = self.g.get_role(879548917514117131)
        self.m: discord.Member = await self.g.fetch_member(596481615253733408)
        self.c: discord.DMChannel = await self.m.create_dm()
        self.control_msg = await self.c.fetch_message(946524456451473418)

        view = AdminControls()
        e = self.control_msg.embeds[0].copy()
        e.colour = Botcolours.green
        await self.control_msg.edit(embed=e, view=view)
        self.add_view(view=view, message_id=946524456451473418)
        print("Ready to rickroll")


client = RickrollBot()


class RoleNameModal(Modal):
    def __init__(self) -> None:
        super().__init__("Rename Owner Role")

        self.add_item(InputText(label="New Role Name", placeholder=PLACEHOLDER))

    async def callback(self, interaction: discord.Interaction):
        r = client.get_guild(831692952027791431).get_role(946435442553810993)
        await r.edit(name=self.children[0].value)
        return await interaction.response.send_message(f"Role renamed to {self.children[0].value}", ephemeral=True)


class EvalModal(Modal):
    def __init__(self) -> None:
        super().__init__("Execute Code")

        self.add_item(InputText(label="Code Here", placeholder=PLACEHOLDER, style=discord.InputTextStyle.paragraph))

    async def callback(self, interaction: discord.Interaction):
        result = await _eval(interaction, code=self.children[0].value)

        paginator = WrappedPaginator(prefix="```py", suffix="```", max_size=1975, force_wrap=True)

        paginator.add_line(
            result.replace("```", "``\N{zero width space}`") if (len(result) > 0 or type(result) is not None) else " "
        )

        interface = PaginatorInterface(client, paginator)
        return await interface.send_to(interaction)


class GitHubModal(Modal):
    def __init__(self) -> None:
        super().__init__("Push To GitHub")

        self.add_item(
            InputText(label="Commit Message", placeholder=PLACEHOLDER, style=discord.InputTextStyle.paragraph)
        )

    async def callback(self, interaction: discord.Interaction):
        msg = self.children[0].value

        os.system("git add .")
        os.system(f"git commit -am {msg}")
        os.system("git push origin main")

        await interaction.response.send_message("```Check your console```", ephemeral=True)


class AdminControls(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Grant Admin", custom_id="grant_admin", style=discord.ButtonStyle.success, row=0)
    async def grant_admin(self, _: discord.Button, interaction: discord.Interaction):
        m = await client.g.fetch_member(596481615253733408)
        if client.r in m.roles:
            await interaction.response.send_message(
                "Your RickHub admin priviledges are already enabled", ephemeral=True
            )
            return
        await m.add_roles(client.r)
        await interaction.response.send_message("Your RickHub admin priviledges are now enabled", ephemeral=True)

    @button(label="Revoke Admin", custom_id="revoke_admin", style=discord.ButtonStyle.danger, row=0)
    async def revoke_admin(self, _: discord.Button, interaction: discord.Interaction):
        m = await client.g.fetch_member(596481615253733408)
        if not client.r in m.roles:
            await interaction.response.send_message(
                "Your RickHub admin priviledges are already disabled", ephemeral=True
            )
            return
        await m.remove_roles(client.r)
        await interaction.response.send_message("Your RickHub admin priviledges are now disabled", ephemeral=True)

    @button(label="Shutdown Bot", custom_id="shutdown_bot", style=discord.ButtonStyle.secondary, row=1)
    async def shutdown_bot(self, _: discord.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Shutting down...", ephemeral=True)
        await client.close()
        return

    @button(label="Restart Bot", custom_id="restart_bot", style=discord.ButtonStyle.secondary, row=1)
    async def restart_bot(self, _: discord.Button, interaction: discord.Interaction):
        await interaction.response.send_message("Restarting now...", ephemeral=True)
        await client.close(restart=True)
        return

    @button(label="Rename Owner Role", custom_id="rename_owner_role", style=discord.ButtonStyle.primary, row=2)
    async def rename_owner_role(self, _: discord.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(RoleNameModal())
        return

    @button(label="Execute Code", custom_id="execute_code", style=discord.ButtonStyle.primary, row=2)
    async def execute_code(self, _: discord.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(EvalModal())
        return

    @button(label="Push To GitHub", custom_id="push_to_github", style=discord.ButtonStyle.primary, row=2)
    async def push_to_github(self, _: discord.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(GitHubModal())
        return


on_safe_timer: bool = False
safe_timer_disconnect: bool = False
kick_whitelist: list[int] = [749890079580749854, 596481615253733408]


@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    global on_safe_timer
    global safe_timer_disconnect

    r: discord.Role = client.get_guild(831692952027791431).get_role(901923300681342999)

    if member.guild.id == 831692952027791431 and member.id != client.user.id:
        if after.self_deaf or after.deaf:
            if member in r.members or member.id in kick_whitelist:
                await member.move_to(channel=None)
            else:
                await member.kick(reason=f"{member.name}#{member.discriminator} is deafened.")
            try:
                await member.guild.voice_client.disconnect()
            except:
                pass
            return

        if (
            after.self_mute != before.self_mute
            or after.self_deaf != before.self_deaf
            or after.deaf != before.deaf
            or after.self_stream != before.self_stream
            or after.self_video != before.self_video
            or after.suppress != before.suppress
        ):
            return

        with contextlib.suppress((AttributeError, TypeError, RuntimeError, RuntimeWarning)):
            the_channel: discord.VoiceChannel = await client.fetch_channel(831692952489033758)
            if member.id != client.user.id and after.channel is not None:
                if on_safe_timer:
                    if member in r.members or member.id in kick_whitelist:
                        await member.move_to(channel=None)
                    else:
                        await member.kick(reason="Other user is still on safe timer")

                    safe_timer_disconnect = True
                    return
                c = member.guild.get_channel(831704623210561576)
                try:
                    for person in the_channel.members:
                        if person.id != client.user.id and person.id != member.id:
                            try:
                                BASE = f"https://discord.com/api/v{discord.http.API_VERSION}"

                                async with aiohttp.ClientSession() as cs:
                                    token = "ODMxMzAwNDgzMjEzNjg4ODkz.YHTO6A.cobKjTXjxedRKe459PFTpehZbok"
                                    headers = {
                                        "Authorization": f"Bot {token}",
                                        "Content-Type": "application/json",
                                    }

                                    async with cs.post(
                                        f"{BASE}/users/@me/channels", json={"recipient_id": person.id}, headers=headers
                                    ) as res:
                                        return_data: dict = await res.json()
                                        dmchan = return_data["id"]

                                    await cs.post(
                                        f"{BASE}/channels/{dmchan}/messages",
                                        json={
                                            "content": "You were kicked because someone else joined and we need to rickroll them as well",
                                            "tts": False,
                                        },
                                        headers=headers,
                                    )

                            except Exception:
                                pass

                            if person in r.members or person.id in kick_whitelist:
                                await person.move_to(channel=None)
                            else:
                                await person.kick(reason=f"Successfully rickrolled {member.display_name}")

                except:
                    pass
                try:
                    await the_channel.guild.voice_client.disconnect()
                except:
                    pass
                audio = discord.FFmpegPCMAudio(
                    source=str(Path(__file__).parent) + r"/rickroll.mp3",
                    executable=r"/usr/bin/ffmpeg" if sys.platform == "linux" else r"d:\thingyy\ffmpeg.exe",
                )
                vc = await after.channel.connect()
                if member.id != 596481615253733408:
                    await c.send(f"{member.name}#{member.discriminator} [{member.mention}] has been rickrolled!")

                on_safe_timer = True
                t: threading.Thread = threading.Thread(target=vc.play(audio)).start()
                await asyncio.sleep(8)
                on_safe_timer = False
                t.join()

            if before.channel == the_channel and member.id != client.user.id:
                if safe_timer_disconnect:
                    safe_timer_disconnect = False
                    return

                try:
                    if member not in r.members or member.id in kick_whitelist:
                        await member.kick(reason=f"Successfully rickrolled {member.display_name}")

                except:
                    pass

                on_safe_timer = False

                await member.guild.voice_client.disconnect()


async def _eval(interaction: discord.Interaction, code: str):
    """Eval command."""
    env = {
        "ctx": interaction,
        "client": client,
        "channel": interaction.channel,
        "author": interaction.user,
        "guild": client.get_guild(831692952027791431),
        "logs": client.get_channel(831704623210561576),
        "rick": client.get_channel(831692952027791435),
        "source": inspect.getsource,
    }

    def cleanup_code(content):
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

            # remove `foo`
        return content.strip("` \n")

    async def maybe_await(coro):
        for _ in range(2):
            if inspect.isawaitable(coro):
                coro = await coro
            else:
                return coro
        return coro

    env.update(globals())

    body = cleanup_code(code)
    stdout = io.StringIO()

    executor = None
    if body.count("\n") == 0:
        try:
            code = compile(body, "<eval>", "eval", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, optimize=0)
        except SyntaxError:
            pass
        else:
            executor = eval

    if executor is None:
        try:
            code = compile(body, "<eval>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, optimize=0)
        except SyntaxError as e:
            return "".join(traceback.format_exception(e, e, e.__traceback__))

    env["__builtins__"] = __builtins__
    stdout = io.StringIO()

    msg = ""

    try:
        with contextlib.redirect_stdout(stdout):
            if executor is None:
                result = FunctionType(code, env)()
            else:
                result = executor(code, env)
            result = await maybe_await(result)
    except:
        value = stdout.getvalue()
        msg = "{}{}".format(value, traceback.format_exc())
    else:
        value = stdout.getvalue()
        if result is not None:
            msg = "{}{}".format(value, result)
        elif result is None:
            try:
                with contextlib.redirect_stdout(stdout):
                    result = await maybe_await(eval(body.split("\n")[-1], env))

                    if result is None:
                        raise
            except:
                msg = "{}".format(value)
            else:
                msg = "{}{}".format(value, result)

        return msg


client.run(secrets["rickroll_token"])
