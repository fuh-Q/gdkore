import asyncio
import contextlib
import logging
import sys
import threading
from pathlib import Path

import discord
from discord.ext import commands

from config.json import Json

logging.basicConfig(level=logging.INFO)
secrets: dict[str, str] = Json.read_json("secrets")


class RickrollBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = False

        super().__init__(command_prefix=".", help_command=None, intents=intents)

    async def close(self, restart: bool = False):
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


class AdminControls(discord.ui.View):
    def __init__(self, client: RickrollBot):
        self.client = client
        self.g: discord.Guild = self.client.get_guild(831692952027791431)
        self.r: discord.Role = self.g.get_role(879548917514117131)
        super().__init__(timeout=None)

    @discord.ui.button(label="Grant Admin", style=discord.ButtonStyle.success, row=0)
    async def grant_admin(self, _: discord.Button, interaction: discord.Interaction):
        m = await self.g.fetch_member(596481615253733408)
        if self.r in m.roles:
            await interaction.response.send_message(
                "Your RickHub admin priviledges are already enabled", ephemeral=True
            )
            return
        await m.add_roles(self.r)
        await interaction.response.send_message(
            "Your RickHub admin priviledges are now enabled", ephemeral=True
        )

    @discord.ui.button(label="Revoke Admin", style=discord.ButtonStyle.danger, row=0)
    async def revoke_admin(self, _: discord.Button, interaction: discord.Interaction):
        m = await self.g.fetch_member(596481615253733408)
        if not self.r in m.roles:
            await interaction.response.send_message(
                "Your RickHub admin priviledges are already disabled", ephemeral=True
            )
            return
        await m.remove_roles(self.r)
        await interaction.response.send_message(
            "Your RickHub admin priviledges are now disabled", ephemeral=True
        )

    @discord.ui.button(label="Shutdown Bot", style=discord.ButtonStyle.secondary, row=1)
    async def restart_bot(self, _: discord.Button, interaction: discord.Interaction):
        await self.client.close()
        return

    @discord.ui.button(label="Restart Bot", style=discord.ButtonStyle.secondary, row=1)
    async def restart_bot(self, _: discord.Button, interaction: discord.Interaction):
        await self.client.close(restart=True)
        return


client = RickrollBot()

on_safe_timer: bool = False
safe_timer_disconnect: bool = False
kick_whitelist: list[int] = [749890079580749854, 596481615253733408]


@client.event
async def on_ready():
    g: discord.Guild = client.get_guild(831692952027791431)
    m: discord.Member = await g.fetch_member(596481615253733408)
    c: discord.DMChannel = await m.create_dm()
    e: discord.Embed = discord.Embed(
        title="RickHub Admin Panel",
        description="Use this to give and remove admin permissions for yourself",
        colour=0x2E3135,
    )
    async for message in c.history(limit=1):
        try:
            await message.delete()
        except discord.HTTPException:
            continue
    await c.send(embed=e, view=AdminControls(client=client))
    for voice in client.voice_clients:
        await voice.disconnect()
    print("Ready to rickroll")


@client.event
async def on_voice_state_update(
    member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
):
    global on_safe_timer
    global safe_timer_disconnect

    r: discord.Role = client.get_guild(831692952027791431).get_role(901923300681342999)

    if member.guild.id == 831692952027791431 and member.id != client.user.id:
        if after.self_deaf or after.deaf:
            if member in r.members or member.id in kick_whitelist:
                await member.move_to(channel=None)
            else:
                await member.kick(
                    reason=f"{member.name}#{member.discriminator} is deafened."
                )
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

        with contextlib.suppress(
            (AttributeError, TypeError, RuntimeError, RuntimeWarning)
        ):
            the_channel: discord.VoiceChannel = await client.fetch_channel(
                831692952489033758
            )
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
                                await person.kick(
                                    reason=f"Successfully rickrolled {member.display_name}"
                                )

                except:
                    pass
                try:
                    await the_channel.guild.voice_client.disconnect()
                except:
                    pass
                audio = discord.FFmpegPCMAudio(
                    source=str(Path(__file__).parent) + r"/rickroll.mp3",
                    executable=r"/usr/bin/ffmpeg"
                    if sys.platform == "linux"
                    else r"d:\thingyy\ffmpeg.exe",
                )
                vc = await after.channel.connect()
                if member.id != 596481615253733408:
                    await c.send(
                        f"{member.name}#{member.discriminator} [{member.mention}] has been rickrolled!"
                    )

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
                        await member.kick(
                            reason=f"Successfully rickrolled {member.display_name}"
                        )

                except:
                    pass

                on_safe_timer = False

                await member.guild.voice_client.disconnect()


client.run(secrets["rickroll_token"])
