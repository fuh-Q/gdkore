from operator import itemgetter
from typing import *

import discord
from discord.ext import commands

from hc_bot import HeistingCultBot


class PointTracker(commands.Cog):
    def __init__(self, client: HeistingCultBot):
        self.client = client  # yes I use "client" stfu
        self.description = "A cog to track heist scouting points"
        self.emoji = self.client.cog_emote

    @commands.Cog.listener()
    async def on_ready(self):
        print("PointTracker cog loaded")

    @commands.group(
        name="points",
        aliases=["pts"],
        brief="View your own point count or that of another user",
        short_doc="Commands to manage point tracking",
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def points(
        self, ctx: commands.Context, member: Optional[commands.MemberConverter] = None
    ):
        member: discord.Member = member if member else ctx.author

        doc: Optional[dict] = await self.client.heist_points.find_one(
            {"_id": member.id}
        )
        if not doc:
            doc = {"points": 0}

        embed = discord.Embed(
            title=f"{member.name}'s point count",
            description=f"`{doc['points']:,}` points",
            colour=0x09DFFF,
        )
        await ctx.reply(embed=embed)

    @points.command(name="add", brief="Add heisting points to a user's profile")
    @commands.check_any(
        commands.is_owner(),
        commands.has_role(892832082278096906),
        commands.has_guild_permissions(administrator=True),
    )
    async def add_points(
        self, ctx: commands.Context, member: commands.MemberConverter, points: int
    ):
        if points == 0:
            await ctx.message.add_reaction("<a:Tick:856832577179222066>")
            return

        member: discord.Member = member

        exists: Optional[dict] = await self.client.heist_points.find_one(
            {"_id": member.id}
        )
        if not exists:
            await self.client.heist_points.insert_one(
                {"_id": member.id, "points": points}
            )
            await ctx.message.add_reaction("<a:Tick:856832577179222066>")
            return

        await self.client.heist_points.update_one(
            {"_id": member.id},
            {"$set": {"_id": member.id, "points": exists["points"] + points}},
            upsert=True,
        )
        await ctx.message.add_reaction("<a:Tick:856832577179222066>")

    @points.command(name="remove", brief="Remove heisting points from a user's profile")
    @commands.check_any(
        commands.is_owner(),
        commands.has_role(892832082278096906),
        commands.has_guild_permissions(administrator=True),
    )
    async def remove_points(
        self, ctx: commands.Context, member: commands.MemberConverter, points: int
    ):
        if points == 0:
            await ctx.message.add_reaction("<a:Tick:856832577179222066>")
            return

        member: discord.Member = member

        exists: Optional[dict] = await self.client.heist_points.find_one(
            {"_id": member.id}
        )
        if not exists:
            await ctx.reply(content=f"The user {member} doesn't exist in the database")
            return

        op: int = exists["points"] - points
        if op > 0:
            await self.client.heist_points.update_one(
                {"_id": member.id},
                {"$set": {"_id": member.id, "points": op}},
                upsert=True,
            )
        else:
            await self.client.heist_points.delete_one({"_id": member.id})
        await ctx.message.add_reaction("<a:Tick:856832577179222066>")

    @points.command(
        name="set", brief="Set a user's heisting points to a specific amount"
    )
    @commands.check_any(
        commands.is_owner(),
        commands.has_role(892832082278096906),
        commands.has_guild_permissions(administrator=True),
    )
    async def set_points(
        self, ctx: commands.Context, member: commands.MemberConverter, points: int
    ):
        member: discord.Member = member

        if points > 0:
            await self.client.heist_points.update_one(
                {"_id": member.id},
                {"$set": {"_id": member.id, "points": points}},
                upsert=True,
            )
        else:
            await self.client.heist_points.delete_one({"_id": member.id})
        await ctx.message.add_reaction("<a:Tick:856832577179222066>")

    @points.command(
        name="leaderboards",
        aliases=["leaderboard", "lb", "rich"],
        brief="Leaderboard of those with the most points",
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def leaderboards(self, ctx: commands.Context):
        a_list: list[dict] = []
        async with ctx.typing():
            async for doc in self.client.heist_points.find():
                a_list.append(doc)

            a_list = sorted(a_list, key=itemgetter("points"), reverse=True)
            e = discord.Embed(
                title=f"Top 10 users in {ctx.guild.name}",
                description="",
                colour=0x09DFFF,
            )

            if a_list == []:
                e.description = "Nobody lol ¯\_(ツ)_/¯"
                return await ctx.reply(embed=e)

            top_10 = False

            for i in range(10):
                try:
                    e.description += f"`{i + 1}.` <@!{a_list[i]['_id']}> - `{a_list[i]['points']:,}` points\n"
                    if a_list[i]["_id"] == ctx.author.id:
                        top_10 = True
                except:
                    break

            if not top_10:
                try:
                    for i in range(len(a_list)):
                        if a_list[i]["_id"] == ctx.author.id:
                            e.description += f"\n`{i + 1}.` <@!{a_list[i]['_id']}> - `{a_list[i]['points']}` points"
                            break

                        if i == len(a_list) - 1:
                            e.description += f"\n`NA.` <@!{ctx.author.id}> - `0` points"

                except:
                    pass

        await ctx.reply(embed=e)


def setup(client: HeistingCultBot):
    client.add_cog(PointTracker(client=client))
