import io
import textwrap
import time
from difflib import SequenceMatcher
from PIL import Image, ImageDraw, ImageFont

import discord
from discord import Interaction
from discord.app_commands import command
from discord.ext import commands

from bot import NotGDKID


class TypeRace(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client
        self.font = ImageFont.truetype("assets/arial.ttf", size=48)
    
    async def get_quote(self) -> str:
        async with self.client.http._HTTPClient__session.get("https://api.quotable.io/random") as res:
            data = await res.json()
            
            return data["content"]

    def words_to_image(self, text: str) -> discord.File:
        img = Image.new(mode="RGBA", size=(1, 1), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        margin = offset = 40
        for line in (lines := textwrap.wrap(text, width=40)):
            draw.text((margin, offset), line, (255, 255, 255), font=self.font)
            offset += self.font.getsize(line)[1]
        
        width = self.font.getsize(max(lines, key=lambda k: len(k)))[0] + margin * 2
        height = (how_tall := self.font.getsize("penis")[1]) * len(lines) + how_tall * 2
        img.resize((width, height))
        
        buffer = io.BytesIO()
        img.save(buffer, "png")
        img.save("output.png")
        buffer.seek(0)
        return discord.File(buffer, "typerace.png")

    def get_accuracy(self, text: str, quote: str) -> float:
        matcher = SequenceMatcher(None, text, quote)
        return matcher.quick_ratio()

    def get_wpm(self, text: str, start: float, accuracy: float) -> float:
        now = time.monotonic()
        return (len(text) / 5) / ((now - start) / 60) * (accuracy / 100)
        #return (len(text) / 5 - (1 - accuracy)) / ((now - start) / 60)

    @commands.Cog.listener()
    async def on_ready(self):
        print("Typerace cog loaded")

    @commands.command(aliases=["tr"])
    @commands.is_owner()
    async def typerace(self, ctx: commands.Context):
        """starts a typerace"""


async def setup(client: NotGDKID):
    await client.add_cog(TypeRace(client=client))
