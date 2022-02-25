import asyncio
import contextlib
import logging
import sys
import threading
from pathlib import Path

import discord
from discord.ext import commands
from discord.ui import InputText, Modal, View, button

from config.json import Json
from config.utils import Botcolours

logging.basicConfig(level=logging.INFO)
secrets: dict[str, str] = Json.read_json("secrets")


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

        await self.control_msg.edit(view=self.persistent_views[0])

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

        self.add_item(InputText(label="New Role Name", placeholder="Enter Something..."))

    async def callback(self, interaction: discord.Interaction):
        r = client.get_guild(831692952027791431).get_role(946435442553810993)
        await r.edit(name=self.children[0].value)
        return await interaction.response.send_message(f"Role renamed to {self.children[0].value}", ephemeral=True)


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
                                await person.send(
                                    "You were kicked because someone else joined and we need to rickroll them as well"
                                )

                            except discord.HTTPException:
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


client.run(secrets["rickroll_token"])
