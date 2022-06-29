import re
from typing import Optional, Union

import discord
from discord.ext import commands

from hc_bot import HeistingCultBot

connected_channel: Optional[discord.TextChannel] = None


class Misc(commands.Cog):
    def __init__(self, client: HeistingCultBot):
        self.client = client
        self.description = "Other stuff"
        self.emoji = "<a:Stars:861487013891014658>"

    @commands.Cog.listener()
    async def on_ready(self):
        print("Misc cog loaded")

    @commands.command(name="ping", brief="Bot latency")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ping(self, ctx: commands.Context):
        await ctx.reply(content=f"Pong! `{round(self.client.latency * 1000)}ms`")

    @commands.command(name="vishtryingtomakeabot", brief="Vish trying to make a bot")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def vishtryingtomakebot(self, ctx: commands.Context):
        await ctx.reply(
            content=f"https://cdn.discordapp.com/attachments/830167112194195516/862005903203762186/unknown.png"
        )

    @commands.command(name="channellink", brief="No", aliases=["cl"])
    @commands.is_owner()
    async def channellink(
        self, ctx: commands.Context, channel_id: Union[discord.TextChannel, int]
    ):
        global connected_channel

        if connected_channel:
            await ctx.reply(f"You are already linked to {connected_channel.mention}")
            return

        if isinstance(channel_id, int):
            channel: discord.TextChannel = self.client.get_channel(channel_id)
        else:
            channel = channel_id

        if not channel:
            await ctx.reply("Channel not found")
            return

        connected_channel = channel
        await ctx.reply(
            f"Successfully linked to {channel.mention}! Type a message prefixed with `> ` to send a message in that channel"
        )
        while True:
            m: discord.Message = await self.client.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.content.startswith("> "),
            )

            if m.content == "> Disconnect.":
                connected_channel = None
                await m.reply("Successfully disconnected")
                return

            if re.search(r"> -m \d+( ?);;( ?).+", m.content, re.I):
                msg = await channel.fetch_message(int(re.search(r"\d+", m.content)[0]))
                await msg.reply(re.split(";;", m.content)[1])
                continue

            await channel.send(m.content[2:])


def setup(client: HeistingCultBot):
    client.add_cog(Misc(client=client))
