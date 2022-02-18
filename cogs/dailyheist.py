import contextlib
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from hc_bot import HeistingCultBot


class DailyHeist(commands.Cog):
    def __init__(self, client: HeistingCultBot):
        self.client = client
        self.description = "The daily heist cog"
        self.emoji = self.client.cog_emote

        self.last_edit: Optional[datetime] = datetime.utcnow()

    @commands.Cog.listener()
    async def on_ready(self):
        print("DailyHeist cog loaded")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        with contextlib.suppress(TypeError):
            if not (datetime.utcnow() - self.last_edit).total_seconds() < 600:
                if (
                    message.author.id == 270904126974590976
                    and len(message.embeds) > 0
                    and message.embeds[0].title.endswith(" is starting a bank robbery")
                    and len(message.components) > 0
                ):
                    heist_channel = await self.client.heist_channel.find_one({})
                    if message.channel.id == heist_channel["_id"]:
                        if not message.channel.name == "🟢・daily-heists":
                            await message.channel.edit(name="🟢・daily-heists", reason="Heist started")
                            await message.add_reaction("🤑")
                            self.last_edit = datetime.utcnow()

    @commands.Cog.listener()
    async def on_message_edit(self, _, after: discord.Message):
        with contextlib.suppress(TypeError):
            if (
                after.author.id == 270904126974590976
                and len(after.embeds) > 0
                and "` people are teaming up to rob **" in after.embeds[0].description
                and len(after.components) > 0
            ):
                heist_channel = await self.client.heist_channel.find_one({})
                if after.channel.id == heist_channel["_id"]:
                    if not after.channel.name == "🔴・daily-heists":
                        await after.channel.edit(name="🔴・daily-heists", reason="Heist ended")
                        self.last_edit = datetime.utcnow()

    @commands.group(
        name="dailyheistchannel",
        aliases=["dhchan", "dailyheistchan"],
        brief="View the set Daily Heist channel",
        short_doc="Commands to manage Daily Heist channel",
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def dailyheistchannels(self, ctx: commands.Context):
        the_channel = ""

        async for doc in self.client.heist_channel.find():
            the_channel = f"<#{doc['_id']}>"

        e = discord.Embed(
            title=f"Daily Heist channel in {ctx.guild.name}",
            description=the_channel if the_channel != "" else "None lol ._.",
            colour=0x09DFFF,
        )
        await ctx.reply(embed=e)

    @dailyheistchannels.command(name="set", aliases=["setchan"], brief="Set the Daily Heist channel")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with ctx.typing():
            await self.client.heist_channel.update_one({"_id": channel.id}, {"$set": {"_id": channel.id}}, upsert=True)

        await ctx.reply(content=f"Successfully set {channel.mention} as the daily heist channel")

    @dailyheistchannels.command(
        name="clear",
        aliases=["reset"],
        brief="Reset the Daily Heist channel",
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def clear_channel(self, ctx: commands.Context):
        async with ctx.typing():
            await self.client.heist_channel.delete_one({})

        await ctx.reply(content=f"Successfully reset the daily heist channel")


def setup(client: HeistingCultBot):
    client.add_cog(DailyHeist(client=client))
