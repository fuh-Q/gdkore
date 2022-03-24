import os
import sys

import discord
from discord.commands import (ApplicationContext, CommandPermission, Option,
                              slash_command)
from discord.ext import commands
from gtts import gTTS

from bot import NotGDKID


class TTS(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("TTS cog loaded")

    @slash_command(
        guild_ids=[890355226517860433],
        default_permissions=False,
        permissions=[CommandPermission(id=596481615253733408, type=2, permission=True)],
    )
    async def tts(self, ctx: ApplicationContext, text: Option(str, "what i'll say", required=True)):
        """say something"""
        await ctx.interaction.response.defer(ephemeral=True)
        vc: discord.VoiceClient = ctx.voice_client
        if vc and not vc.is_playing():
            try:
                gTTS(text=text, lang="en", slow=False).save(fp := f"tts.mp3")

            except Exception as e:
                print(e)
                return await ctx.respond("something went wrong there", ephemeral=True)

            src = discord.FFmpegPCMAudio(
                source=fp, executable=r"/usr/bin/ffmpeg" if sys.platform == "linux" else r"d:\thingyy\ffmpeg.exe"
            )
            vc.play(src, after=lambda _: os.remove("tts.mp3"))


def setup(client: NotGDKID):
    client.add_cog(TTS(client=client))
