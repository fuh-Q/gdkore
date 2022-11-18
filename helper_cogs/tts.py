import asyncio
import os
import sys

import discord
from discord import Interaction
from discord.app_commands import command, default_permissions, describe, guild_only
from discord.ext import commands

from gtts import gTTS

from helper_bot import NotGDKID


class TTS(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @command(name="tts")
    @describe(text="what i'll say")
    @guild_only()
    async def tts(self, interaction: Interaction, text: str):
        """say something"""
        if (
            interaction.user.id not in self.client.owner_ids
            or not interaction.guild
            or not interaction.guild.voice_client
        ):
            return await interaction.response.send_message(
                "no", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        vc = interaction.guild.voice_client
        assert isinstance(vc, discord.VoiceClient)

        if vc and not vc.is_playing():
            try:
                await asyncio.to_thread(gTTS(text=text, slow=False).save, fp := "tts.mp3")

            except Exception as e:
                print(e)
                return await interaction.response.send_message(
                    "something went wrong there", ephemeral=True
                )

            src = discord.FFmpegPCMAudio(
                source=fp,
                executable=r"/usr/bin/ffmpeg"
                if sys.platform == "linux"
                else r"d:\thingyy\ffmpeg.exe",
            )
            vc.play(src, after=lambda _: os.remove("tts.mp3"))

        await interaction.delete_original_response()


async def setup(client: NotGDKID):
    await client.add_cog(TTS(client=client))