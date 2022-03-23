import discord
from discord.ext import commands
from discord.commands import slash_command, ApplicationContext, Option, CommandPermission

from bot import NotGDKID

from gtts import gTTS
import os
import sys


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
    async def tts(
        self,
        ctx: ApplicationContext,
        text: Option(
            str,
            "what i'll say",
            required=True
        )
    ):
        """say something"""
        await ctx.interaction.response.defer(ephemeral=True)
        if ctx.voice_client and not ctx.voice_client.is_playing():
            try:
                gTTS(text=text, lang="en", slow=False).save(fp := f"tts.mp3")
            
            except Exception as e:
                print(e)
                return await ctx.respond("something went wrong there", ephemeral=True)
            
            src = discord.FFmpegPCMAudio(source=fp, executable=r"/usr/bin/ffmpeg" if sys.platform == "linux" else r"d:\thingyy\ffmpeg.exe")
            ctx.voice_client.play(src, after = lambda _: os.remove("tts.mp3"))


def setup(client: NotGDKID):
    client.add_cog(TTS(client=client))
