import os
import sys

import discord
from discord import Interaction
from discord.app_commands import command, describe
from discord.ext import commands
from gtts import gTTS

from bot import NotGDKID


class TTS(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("TTS cog loaded")

    @command()
    @describe(text="what i'll say")
    async def tts(self, interaction: Interaction, text: str):
        """say something"""
        if interaction.user.id != 596481615253733408:
            return await interaction.response.send_message("soon™️", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        vc: discord.VoiceClient = interaction.guild.voice_client
        if vc and not vc.is_playing():
            try:
                gTTS(text=text, lang="en", slow=False).save(fp := f"tts.mp3")

            except Exception as e:
                print(e)
                return await interaction.response.send_message("something went wrong there", ephemeral=True)

            src = discord.FFmpegPCMAudio(
                source=fp, executable=r"/usr/bin/ffmpeg" if sys.platform == "linux" else r"d:\thingyy\ffmpeg.exe"
            )
            vc.play(src, after=lambda _: os.remove("tts.mp3"))


async def setup(client: NotGDKID):
    await client.add_cog(TTS(client=client))
