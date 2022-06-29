import discord
from discord.ext import commands
from fuzzy_match import match

from hc_bot import HeistingCultBot


class PingThing(commands.Cog):
    def __init__(self, client: HeistingCultBot):
        self.client = client
        self.description = "An unfriendly heist ping cog"
        self.emoji = self.client.cog_emote
        self.RoleConverter = commands.RoleConverter()

    @commands.Cog.listener()
    async def on_ready(self):
        print("Ping cog loaded")

    @commands.command(name="hp", brief="Ping the normal Unfriendly Heist Ping")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ping_normal(self, ctx: commands.Context, *, message: str):
        ping_here = await self.client.ping_channels.find_one({"_id": ctx.channel.id})
        if not ping_here:
            await ctx.reply(content="Doesn't work here mate")
            return

        doc = await self.client.ping_roles.find_one({"ping_for": "Default"})
        if not doc:
            await ctx.reply(content="Looks like that isn't set up yet")
            return

        role: discord.Role = await self.RoleConverter.convert(ctx, str(doc["_id"]))
        content = f"{role.mention} {ctx.author.name} has a heist for you!\n> {message}"

        await ctx.message.delete()
        await ctx.send(content=content)

    @commands.command(name="h5", brief="Ping the 5m+ Unfriendly Heist Ping")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ping_h5(self, ctx: commands.Context, *, message: str):
        ping_here = await self.client.ping_channels.find_one({"_id": ctx.channel.id})
        if not ping_here:
            await ctx.reply(content="Doesn't work here mate")
            return

        doc = await self.client.ping_roles.find_one({"ping_for": "5m+"})
        other_doc = await self.client.ping_roles.find_one({"ping_for": "Default"})
        if not doc or not other_doc:
            await ctx.reply(content="Looks like that isn't set up yet")
            return

        role: discord.Role = await self.RoleConverter.convert(ctx, str(doc["_id"]))
        other_role: discord.Role = await self.RoleConverter.convert(ctx, str(other_doc["_id"]))
        content = (
            f"{other_role.mention} {role.mention} {ctx.author.name} has a __***5m+***__ heist for you!\n> {message}"
        )

        await ctx.message.delete()
        await ctx.send(content=content)

    @commands.group(
        name="pingroles",
        brief="View the set Unfriendly Heist Ping roles",
        short_doc="Commands to manage Unfriendly Heist Ping roles",
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def pingroles(self, ctx: commands.Context):
        a_list: list[dict] = []

        async for doc in self.client.ping_roles.find():
            a_list.append(f"<@&{doc['_id']}> - `{doc['ping_for']} ping`")

        e = discord.Embed(
            title=f"Unfriendly Heist Ping roles in {ctx.guild.name}",
            description="\n".join(a_list) if len(a_list) > 0 else "None lul ._.",
            colour=0x09DFFF,
        )
        await ctx.reply(embed=e)

    @pingroles.command(name="set", brief="Set the Unfriendly Heist Ping for the default amount")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def set_ping(self, ctx: commands.Context, *, role: str):
        async with ctx.typing():
            try:
                role: discord.Role = await self.RoleConverter.convert(ctx, role)
            except:
                mach = match.extractOne(role, ctx.guild.roles, score_cutoff=0.2)
                if not mach:
                    await ctx.reply(content="Couldn't find a role with the query given. Sorry")
                    return

                role: discord.Role = mach[0]

            await self.client.ping_roles.update_one(
                {"_id": role.id},
                {"$set": {"_id": role.id, "ping_for": "Default"}},
                upsert=True,
            )

        await ctx.reply(
            content=f"Successfully set {role.mention} as the ping role for normal heists",
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        )

    @pingroles.command(name="seth5", brief="Set the Unfriendly Heist Ping for 5m+ heists")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def set_h5_ping(self, ctx: commands.Context, *, role: str):
        async with ctx.typing():
            try:
                role: discord.Role = await self.RoleConverter.convert(ctx, role)
            except:
                mach = match.extractOne(role, ctx.guild.roles, score_cutoff=0.2)
                if not mach:
                    await ctx.reply(content="Couldn't find a role with the query given. Sorry")
                    return

                role: discord.Role = mach[0]

            await self.client.ping_roles.update_one(
                {"_id": role.id},
                {"$set": {"_id": role.id, "ping_for": "5m+"}},
                upsert=True,
            )

        await ctx.reply(
            content=f"Successfully set {role.mention} as the ping role for 5m+ heists",
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        )

    @pingroles.command(name="clear", aliases=["reset"], brief="Clear all Unfriendly Heist Ping roles")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def clear_pingroles(self, ctx: commands.Context):
        async with ctx.typing():
            async for _ in self.client.ping_roles.find():
                await self.client.ping_roles.delete_one({})

        await ctx.reply(content="Successfully cleared all ping roles")

    @commands.group(
        name="pingchannels",
        aliases=["pingchans"],
        brief="View the set Unfriendly Heist Ping channels",
        short_doc="Commands to manage Unfriendly Heist Ping channels",
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def pingchannels(self, ctx: commands.Context):
        a_list: list[dict] = []

        async for doc in self.client.ping_channels.find():
            a_list.append(f"<#{doc['_id']}>")

        e = discord.Embed(
            title=f"Unfriendly Heist Ping channels in {ctx.guild.name}",
            description="\n".join(a_list) if len(a_list) > 0 else "None lol ._.",
            colour=0x09DFFF,
        )
        await ctx.reply(embed=e)

    @pingchannels.command(name="add", aliases=["addchan"], brief="Add an Unfriendly Heist Ping channel")
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def add_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with ctx.typing():
            await self.client.ping_channels.update_one({"_id": channel.id}, {"$set": {"_id": channel.id}}, upsert=True)

        await ctx.reply(content=f"Successfully set {channel.mention} as a ping channel")

    @pingchannels.command(
        name="remove",
        aliases=["rm", "rmchan"],
        brief="Remove an Unfriendly Heist Ping channel",
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def remove_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        async with ctx.typing():
            await self.client.ping_channels.delete_one({"_id": channel.id})

        await ctx.reply(content=f"Successfully removed {channel.mention} as a ping channel")

    @pingchannels.command(
        name="clear",
        aliases=["reset"],
        brief="Clear all Unfriendly Heist Ping channels",
    )
    @commands.check_any(commands.is_owner(), commands.has_guild_permissions(administrator=True))
    async def clear_pingroles(self, ctx: commands.Context):
        async with ctx.typing():
            async for _ in self.client.ping_channels.find():
                await self.client.ping_channels.delete_one({})

        await ctx.reply(content="Successfully cleared all ping channels")


def setup(client: HeistingCultBot):
    client.add_cog(PingThing(client=client))
