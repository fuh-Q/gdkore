import asyncio
import random
import re
from operator import itemgetter
from typing import *

import discord
from discord.ext import commands
from fuzzy_match import match

from config.utils import CHOICES
from hc_bot import HeistingCultBot


def convert_to_int(amount: str) -> Optional[int]:
    try:
        amountInt = int(amount)
    except:
        try:
            conversionList = {
                "k": 1000,
                "K": 1000,
                "m": 1000000,
                "M": 1000000,
                "b": 1000000000,
                "B": 1000000000,
            }
            amountInt = int(amount[:-1]) * conversionList[amount[-1]]
        except:
            try:
                eConversionList = {
                    "e0": 1,
                    "e1": 10,
                    "e2": 100,
                    "e3": 1000,
                    "e4": 10000,
                    "e5": 100000,
                    "e6": 1000000,
                    "e7": 10000000,
                    "e8": 100000000,
                    "e9": 1000000000,
                }
                amountInt = int(amount[:-2]) * eConversionList[amount[-2:]]
            except:
                return None

    return amountInt


class AreUSureLoL(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        self.timeout = 30
        self.owner = ctx.author
        self.clear = False
        super().__init__(timeout=self.timeout)

    async def interaction_check(self, interaction: discord.Interaction):
        """Check that determines whether this interaction should be honored"""
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()

    @discord.ui.button(label="Yessirrrrr", emoji="💀", style=discord.ButtonStyle.success)
    async def clear_user(self, button: discord.Button, interaction: discord.Interaction):
        self.clear = True
        self.clear_items()
        self.stop()

    @discord.ui.button(label="Actually nah", style=discord.ButtonStyle.danger)
    async def no_clear(self, button: discord.Button, interaction: discord.Interaction):
        self.clear_items()
        self.stop()


class DonoTracker(commands.Cog):
    def __init__(self, client: HeistingCultBot):
        self.client = client
        self.description = "A cog to track DMC donations"
        self.emoji = self.client.cog_emote
        self.MemberConverter = commands.MemberConverter()
        self.RoleConverter = commands.RoleConverter()
        self.dono_channels = [896490637485043812]
        self.dono_logging = None
        self.dono_regex = re.compile(
            r"<@!?[^&]\d+> You gave .+ \*\*⏣ (\d|,)+\*\* after a 3% tax rate, now you have ⏣ (\d|,)+ and they've got ⏣ (\d|,)+"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        print("Dono Tracker cog loaded")
        async for doc in self.client.dono_channels.find():
            """
            Faster donation detection (i.e. faster than querying the db everytime)
            """
            self.dono_channels.append(doc["_id"])

        async for doc in self.client.dono_logging.find():
            """
            Same purpose as above
            everytime a config command is invoked
            we update the attribute with the updated stuff from the db
            """
            self.dono_logging = self.client.get_channel(doc["_id"])

        guild = self.client.get_guild(self.client.main_guild_id)

        async for doc in self.client.dono_roles.find():
            """
            In case they have for example event donation roles
            and they forget to take it off the bot
            it just keeps the db cleaner yknow?
            """
            do_continue = False
            for role in guild.roles:
                if role.id == doc["_id"]:
                    do_continue = True
                    break
            if do_continue:
                continue
            else:
                await self.client.dono_roles.delete_one({"_id": doc["_id"]})

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.TextChannel):
        """Pretty self explanatory"""
        await self.client.dono_channels.delete_one({"_id": channel.id})

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Donation detection magik"""
        if (
            self.dono_regex.search(message.content)
            and message.author.id == 270904126974590976
            and message.channel.id in self.dono_channels
        ):
            ctx: commands.Context = await self.client.get_context(
                message
            )  # Need this for the converters (MemberConverter, etc)

            number: int = int(  # The amount donated
                re.search(r"\*\*⏣ \d+\*\*", message.content.replace(",", ""))[0][4:-2]
            )
            donor: discord.Member = await self.MemberConverter.convert(  # The person who donated
                ctx, re.search(r"<@!?[^&]\d+>", message.content)[0]
            )

            exists: Optional[dict] = await self.client.donos.find_one(
                {"_id": donor.id}
            )  # Fetch the donor's previously logged donations
            if not exists:  # If none found
                await self.client.donos.insert_one({"_id": donor.id, "donated": number, "donations": 1})
                e = discord.Embed(
                    title=f"Thank you for donating!",
                    description=f"Donations: `1`\nTotal Donated: `⏣ {number:,}`",
                    colour=0x09DFFF,
                )
                await message.reply(content=f"{donor.mention}", embed=e)
                if self.dono_logging:
                    e.title = f"{donor.name} has donated!"
                    e.description = f"Amount donated: `⏣ {number:,}`\n" + e.description
                    await self.dono_logging.send(embed=e)

                list_of_docs: list[dict] = []

                async for doc in self.client.dono_roles.find():
                    list_of_docs.append(doc)

                sorted_list_of_docs = sorted(list_of_docs, key=itemgetter("milestone"))

                for i in range(len(sorted_list_of_docs)):
                    if number > sorted_list_of_docs[i]["milestone"]:
                        await donor.add_roles(message.guild.get_role(sorted_list_of_docs[i]["_id"]))
                        await asyncio.sleep(0.5)
                return

            donated = exists["donated"] + number
            donations = exists["donations"] + 1

            await self.client.donos.update_one(
                {"_id": donor.id},
                {"$set": {"_id": donor.id, "donated": donated, "donations": donations}},
                upsert=True,
            )

            e = discord.Embed(
                title="Thank you for donating!",
                description=f"Donations: `{donations:,}`\nTotal Donated: `⏣ {donated:,}`",
                colour=0x09DFFF,
            )
            await message.reply(content=f"{donor.mention}", embed=e)
            if self.dono_logging:
                e.title = f"{donor.name} has donated!"
                e.description = f"Amount donated: `⏣ {number:,}`\n" + e.description
                await self.dono_logging.send(embed=e)

            list_of_docs: list[dict] = []

            async for doc in self.client.dono_roles.find():
                list_of_docs.append(doc)

            sorted_list_of_docs = sorted(list_of_docs, key=itemgetter("milestone"))

            for i in range(len(sorted_list_of_docs)):
                if donated > sorted_list_of_docs[i]["milestone"]:
                    await donor.add_roles(message.guild.get_role(sorted_list_of_docs[i]["_id"]))
                    await asyncio.sleep(0.5)

    @commands.group(
        name="donations",
        aliases=["donos"],
        brief="See a member's DMC donations",
        short_doc="Commands for DMC donations",
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def donations(self, ctx: commands.Context, member: commands.MemberConverter = None):
        if not member:
            member = ctx.author

        member: discord.Member = member

        doc = await self.client.donos.find_one({"_id": member.id})
        if not doc:
            doc = {"donations": 0, "donated": 0}

        e = discord.Embed(
            title=f"{member.name}'s donations",
            description=f"Donations: `{doc['donations']:,}`\nTotal Donated: `⏣ {doc['donated']:,}`",
            colour=0x09DFFF,
        )
        await ctx.reply(embed=e)

    @donations.command(name="add", brief="Add to a user's donated amount")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def add_dono(
        self,
        ctx: commands.Context,
        member: commands.MemberConverter,
        *,
        amountInt: convert_to_int,
    ):
        member: discord.Member = member

        if not amountInt:
            await ctx.reply(content="Couldn't convert your input into an integer")
            return

        doc = await self.client.donos.find_one({"_id": member.id})
        if not doc:
            doc = {
                "donated": 0,
                "donations": 0,
            }

        await self.client.donos.update_one(
            {"_id": member.id},
            {
                "$set": {
                    "_id": member.id,
                    "donated": doc["donated"] + amountInt,
                    "donations": doc["donations"],
                }
            },
            upsert=True,
        )

        await ctx.reply(content=f"Successfully added `⏣ {amountInt:,}` to {member.name}'s donations")

        list_of_docs: list[dict] = []

        async for document in self.client.dono_roles.find():
            list_of_docs.append(document)

        sorted_list_of_docs = sorted(list_of_docs, key=itemgetter("milestone"))
        new_amt = doc["donated"] + amountInt

        for i in range(len(sorted_list_of_docs)):
            if (
                new_amt > sorted_list_of_docs[i]["milestone"]
                and not ctx.guild.get_role(sorted_list_of_docs[i]["_id"]) in member.roles
            ):
                await member.add_roles(ctx.guild.get_role(sorted_list_of_docs[i]["_id"]))
                await asyncio.sleep(0.5)

    @donations.command(name="remove", brief="Remove from a user's donated amount")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def remove_dono(
        self,
        ctx: commands.Context,
        member: commands.MemberConverter,
        *,
        amountInt: convert_to_int,
    ):
        member: discord.Member = member

        if not amountInt:
            await ctx.reply(content="Couldn't convert your input into an integer")
            return

        doc = await self.client.donos.find_one({"_id": member.id})
        if not doc:
            doc = {
                "donated": 0,
                "donations": 0,
            }

        await self.client.donos.update_one(
            {"_id": member.id},
            {
                "$set": {
                    "_id": member.id,
                    "donated": doc["donated"] - amountInt if doc["donated"] - amountInt > 0 else 0,
                    "donations": doc["donations"],
                }
            },
            upsert=True,
        )

        await ctx.reply(content=f"Successfully removed `⏣ {amountInt:,}` from {member.name}'s donations")

        list_of_docs: list[dict] = []

        async for document in self.client.dono_roles.find():
            list_of_docs.append(document)

        sorted_list_of_docs = sorted(list_of_docs, key=itemgetter("milestone"))
        new_amt = doc["donated"] - amountInt

        for i in range(len(sorted_list_of_docs)):
            if (
                new_amt < sorted_list_of_docs[i]["milestone"]
                and ctx.guild.get_role(sorted_list_of_docs[i]["_id"]) in member.roles
            ):
                await member.remove_roles(ctx.guild.get_role(sorted_list_of_docs[i]["_id"]))
                await asyncio.sleep(0.5)

    @donations.command(name="set", brief="Set a user's donations to a specific amount")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def set_dono(
        self,
        ctx: commands.Context,
        member: commands.MemberConverter,
        *,
        amountInt: convert_to_int,
    ):
        member: discord.Member = member

        if not amountInt:
            await ctx.reply(content="Couldn't convert your input into an integer")
            return

        doc = await self.client.donos.find_one({"_id": member.id})
        if not doc:
            doc = {
                "donated": 0,
                "donations": 0,
            }

        await self.client.donos.update_one(
            {"_id": member.id},
            {
                "$set": {
                    "_id": member.id,
                    "donated": amountInt if amountInt > 0 else 0,
                    "donations": doc["donations"],
                }
            },
            upsert=True,
        )

        await ctx.reply(content=f"Successfully set {member.name}'s donation amount to `⏣ {amountInt:,}`")

        list_of_docs: list[dict] = []

        async for document in self.client.dono_roles.find():
            list_of_docs.append(document)

        sorted_list_of_docs = sorted(list_of_docs, key=itemgetter("milestone"))
        new_amt = doc["donated"] - amountInt

        for i in range(len(sorted_list_of_docs)):
            if (
                new_amt < sorted_list_of_docs[i]["milestone"]
                and ctx.guild.get_role(sorted_list_of_docs[i]["_id"]) in member.roles
            ):
                await member.remove_roles(ctx.guild.get_role(sorted_list_of_docs[i]["_id"]))
                await asyncio.sleep(0.5)

        new_amt = doc["donated"] + amountInt

        for i in range(len(sorted_list_of_docs)):
            if (
                new_amt > sorted_list_of_docs[i]["milestone"]
                and not ctx.guild.get_role(sorted_list_of_docs[i]["_id"]) in member.roles
            ):
                await member.add_roles(ctx.guild.get_role(sorted_list_of_docs[i]["_id"]))
                await asyncio.sleep(0.5)

    @donations.command(name="reset", aliases=["clear"], brief="Clear a user's donations")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def reset_dono(self, ctx: commands.Context, member: commands.MemberConverter):
        member: discord.Member = member

        e = discord.Embed(
            title=f"Clear {member.name}'s donations",
            description="Are you sure you want to do this?",
            colour=discord.Color.yellow(),
        )
        view = AreUSureLoL(ctx=ctx)
        m = await ctx.send(embed=e, view=view)
        await view.wait()
        if view.clear:
            e.colour = 0x2ECC70
            e.description = f"Successfully reset {member.name}'s donations"
            await m.edit(embed=e, view=None)
            await self.client.donos.delete_one({"_id": member.id})
            await ctx.reply(content=f"Successfully reset {member.name}'s donations")

            list_of_docs: list[dict] = []

            async for document in self.client.dono_roles.find():
                list_of_docs.append(document)

            sorted_list_of_docs = sorted(list_of_docs, key=itemgetter("milestone"))
            for i in range(len(sorted_list_of_docs)):
                if ctx.guild.get_role(sorted_list_of_docs[i]["_id"]) in member.roles:
                    await member.remove_roles(ctx.guild.get_role(sorted_list_of_docs[i]["_id"]))
                    await asyncio.sleep(0.5)
            return

        e.colour = 0x000000
        e.description = "Alright I guess no fireworks tonight"
        await m.edit(embed=e, view=None)
        await ctx.reply(content="Alright I guess no fireworks tonight")

    @donations.command(name="leaderboard", aliases=["lb"], brief="Display the top donated 10 users")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dono_leaderboards(self, ctx: commands.Context):
        a_list: list[dict] = []
        async with ctx.typing():
            async for doc in self.client.donos.find():
                a_list.append(doc)

            a_list = sorted(a_list, key=itemgetter("donated"), reverse=True)
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
                    e.description += f"`{i + 1}.` <@!{a_list[i]['_id']}> - `⏣ {a_list[i]['donated']:,}`\n"
                    if a_list[i]["_id"] == ctx.author.id:
                        top_10 = True
                except:
                    break

            if not top_10:
                try:
                    for i in range(len(a_list)):
                        if a_list[i]["_id"] == ctx.author.id:
                            e.description += f"\n`{i + 1}.` <@!{a_list[i]['_id']}> - `⏣ {a_list[i]['donated']:,}`\n"
                            break

                        if i == len(a_list) - 1:
                            e.description += f"\n`NA.` <@!{ctx.author.id}> - `⏣ 0`"

                except:
                    pass

        await ctx.reply(embed=e)

    @commands.group(
        name="donationchannels",
        aliases=["donochannels", "donochans"],
        brief="Display the set donation channels",
        short_doc="Commands to manage donation channels",
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def donationchannels(self, ctx: commands.Context):
        async with ctx.typing():
            a_list: list[Optional[discord.TextChannel]] = []

            async for doc in self.client.dono_channels.find():
                a_list.append(self.client.get_channel(doc["_id"]))

            e = discord.Embed(
                title=f"Donation channels in {ctx.guild.name}",
                description="{0}".format(
                    "\n".join([channel.mention for channel in a_list]) if len(a_list) > 0 else "None lol ¯\_(ツ)_/¯"
                ),
                colour=0x09DFFF,
            )

        await ctx.reply(embed=e)

    @donationchannels.command(
        name="add",
        aliases=["addchan"],
        brief="Add a channel where donations will be tracked",
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def add_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with ctx.typing():
            await self.client.dono_channels.update_one({"_id": channel.id}, {"$set": {"_id": channel.id}}, upsert=True)
            self.dono_channels.clear()

            async for doc in self.client.dono_channels.find():
                self.dono_channels.append(doc["_id"])

        await ctx.reply(content=f"Successfully set {channel.mention} as a donation channel")

    @donationchannels.command(
        name="remove",
        aliases=["rm", "rmchan"],
        brief="Remove a channel where donations are be tracked",
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def remove_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with ctx.typing():
            await self.client.dono_channels.delete_one({"_id": channel.id})
            self.dono_channels.clear()

            async for doc in self.client.dono_channels.find():
                self.dono_channels.append(doc["_id"])

        await ctx.reply(content=f"Successfully removed {channel.mention} as a donation channel")

    @donationchannels.command(
        name="removeall",
        aliases=["rmall", "clear"],
        brief="Remove every channel where donations are be tracked",
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def removeall_channels(self, ctx: commands.Context):
        async with ctx.typing():
            async for _ in self.client.dono_channels.find():
                await self.client.dono_channels.delete_one({})

        await ctx.reply(content=f"Successfully removed all donation channels")

    @commands.group(
        name="donationroles",
        aliases=["donoroles"],
        brief="Display the set donation roles",
        short_doc="Commands to manage donation roles",
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def donationroles(self, ctx: commands.Context):
        async with ctx.typing():
            a_list: list[str] = []

            async for doc in self.client.dono_roles.find():
                a_list.append(f"{ctx.guild.get_role(doc['_id']).mention} - `⏣ {doc['milestone']:,}`")

            e = discord.Embed(
                title=f"Donation roles in {ctx.guild.name}",
                description="{0}".format("\n".join([r for r in a_list]) if len(a_list) > 0 else "None lmfao ¯\_(ツ)_/¯"),
                colour=0x09DFFF,
            )
        await ctx.reply(embed=e)

    @donationroles.command(name="add", brief="Add a donation milestone role")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def add_role(self, ctx: commands.Context, milestone: convert_to_int, *, role: str):
        if not milestone:
            await ctx.reply(content="Couldn't convert your input into an integer")
            return

        try:
            role: discord.Role = await self.RoleConverter.convert(ctx, role)
        except:
            mach = match.extractOne(role, ctx.guild.roles, score_cutoff=0.2)
            if not mach:
                await ctx.reply(content="Couldn't find a role with the query given. Sorry")
                return

            role: discord.Role = mach[0]

        await self.client.dono_roles.update_one(
            {"_id": role.id},
            {
                "$set": {
                    "_id": role.id,
                    "milestone": milestone,
                }
            },
            upsert=True,
        )

        await ctx.reply(
            content=f"Successfully set {role.mention} as a milestone role for donating `⏣ {milestone:,}`",
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        )

    @donationroles.command(name="remove", brief="Remove a donation milestone role")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def remove_role(self, ctx: commands.Context, *, role: str):
        try:
            role: discord.Role = await self.RoleConverter.convert(ctx, role)
        except:
            mach = match.extractOne(role, ctx.guild.roles, score_cutoff=0.2)
            if not mach:
                await ctx.reply(content="Couldn't find a role with the query given. Sorry")
                return

            role: discord.Role = mach[0]

        await self.client.dono_roles.delete_one({"_id": role.id})

        await ctx.reply(
            content=f"Successfully removed {role.mention} as a donation milestone role",
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        )

    @donationroles.command(name="reset", aliases=["clear"], brief="Remove all donation milestone roles")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def remove_all_roles(self, ctx: commands.Context):
        async with ctx.typing():
            async for _ in self.client.dono_roles.find():
                await self.client.dono_roles.delete_one({})

        await ctx.reply(content="Successfully removed all donation roles")

    @commands.group(
        name="loggingchannel",
        aliases=["logchan"],
        brief="See the set donation logging channel",
        short_doc="Commands to configure the donation log channel",
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def loggingchannel(self, ctx: commands.Context):
        async for doc in self.client.dono_logging.find():
            e = discord.Embed(
                title=f"Donation log channel in {ctx.guild.name}",
                description=f"<#{doc['_id']}>",
                colour=0x09DFFF,
            )

        await ctx.reply(embed=e)

    @loggingchannel.command(
        name="setloggingchannel",
        aliases=["setlogchan", "setlog"],
        brief="Set a donation logging channel",
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def setloggingchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        async for _ in self.client.dono_logging.find():
            await self.client.dono_logging.delete_one({})

        await self.client.dono_logging.insert_one({"_id": channel.id})

        self.dono_logging = channel

        await ctx.reply(content=f"Donations will now be logged in {channel.mention}")


def setup(client: HeistingCultBot):
    client.add_cog(DonoTracker(client=client))
