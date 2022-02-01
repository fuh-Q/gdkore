import time

import discord
from discord.ext import commands

from bot import BanBattler
from config.json import Json
from config.utils import BattlerCog


class Dev(BattlerCog):
    def __init__(self, client: BanBattler):
        self.client = client
        self.emoji = "<a:gdkid:868976838112841760>"

    @commands.Cog.listener()
    async def on_ready(self):
        print("Dev cog loaded")

    @commands.command(aliases=["bl"], hidden=True, brief="Add a user to the blacklist")
    @commands.is_owner()
    async def blacklist(self, ctx, user: discord.Member, *, reason: str = "None given"):
        await self.client.blacklists.update_one(
            {"_id": user.id}, {"$set": {"_id": user.id}}, upsert=True
        )
        if user.id == self.client.owner_id:
            await user.send("I can't ban you lol")
            return await ctx.message.add_reaction(self.client.yes)
        try:
            await user.send(
                "You have been bot banned. If you believe this is a mistake, contact `˞˞#0069`\n\n**REASON**\n{0}".format(
                    reason
                )
            )
        except:
            await ctx.reply("User banned. I couldn't DM them")
        await ctx.message.add_reaction(self.client.yes)

    @commands.command(
        aliases=["gbl"], hidden=True, brief="Add a server to the blacklist"
    )
    @commands.is_owner()
    async def guildblacklist(
        self, ctx, guild: discord.Guild, *, reason: str = "None given"
    ):
        await self.client.guild_blacklists.update_one(
            {"_id": guild.id},
            {"$set": {"_id": guild.id, "name": guild.name, "owner": guild.owner_id}},
            upsert=True,
        )
        try:
            user = guild.get_member(guild.owner_id)
            await guild.leave()
            await user.send(
                "Your server, `{0}`, has been bot banned. If you believe this is a mistake, contact `˞˞#0069`\n\n**REASON**\n{1}".format(
                    guild.name, reason
                )
            )
        except:
            await guild.leave()
            await ctx.reply("Guild banned. I couldn't DM the owner")
        await ctx.message.add_reaction(self.client.yes)

    @commands.command(
        aliases=["wl"], hidden=True, brief="Remove a user from the blacklist"
    )
    @commands.is_owner()
    async def whitelist(self, ctx, user: discord.User):
        is_blacklisted = await self.client.blacklists.find_one({"_id": user.id})
        if is_blacklisted:
            await self.client.blacklists.delete_one({"_id": user.id})
            try:
                await user.send(
                    "Congrats, you've been unbanned. Don't pull shit like that again"
                )
            except:
                await ctx.reply("User unbanned. I couldn't DM them")
            await ctx.message.add_reaction(self.client.yes)
        else:
            await ctx.message.add_reaction(self.client.no)

    @commands.command(
        aliases=["gwl"], hidden=True, brief="Remove a server from the blacklist"
    )
    @commands.is_owner()
    async def guildwhitelist(self, ctx, guild: int):
        is_guild_blacklisted = await self.client.guild_blacklists.find_one(
            {"_id": guild}
        )
        if is_guild_blacklisted:
            await self.client.guild_blacklists.delete_one({"_id": guild})
            try:
                user = await self.client.fetch_user(is_guild_blacklisted["owner"])
                await user.send(
                    "Congrats your server, `{0}`, has been unbanned. Don't pull shit like that again".format(
                        is_guild_blacklisted["name"]
                    )
                )
            except:
                await ctx.reply("Guild unbanned. I couldn't DM the owner")
            await ctx.message.add_reaction(self.client.yes)
        else:
            await ctx.message.add_reaction(self.client.no)

    @commands.command(
        aliases=["servers"], hidden=True, brief="Get the bot's server count"
    )
    @commands.is_owner()
    async def guilds(self, ctx: commands.Context):
        command = self.client.get_command("repl exec")
        await ctx.invoke(
            command,
            code='"".join(["\\n".join(["{0.name}: {1} members | {0.id}".format(g, len([m for m in g.members if not m.bot])) for g in client.guilds]), f"\\n\\n{len(client.guilds)} servers"])',
        )

    @commands.command(hidden=True, brief="Shut down the bot")
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        e = discord.Embed(description="👋 cya")
        await ctx.reply(embed=e)
        await self.client.close()

    @commands.command(hidden=True, brief="Restart the bot")
    @commands.is_owner()
    async def restart(self, ctx: commands.Context):
        e = discord.Embed(description="<a:loading:937145488493379614> Aight brb")
        msg = await ctx.reply(embed=e)
        Json.write_json(
            {
                "id": msg.id,
                "chan_id": msg.channel.id if ctx.guild else 0,
                "now": time.monotonic(),
            },
            "restart",
        )
        await self.client.close(restart=True)

    @commands.command(name="hi", brief='Say "Hi" to the bot', hidden=True)
    @commands.is_owner()
    async def hi(self, ctx: commands.Context):
        await ctx.reply("hi")


def setup(client: BanBattler):
    client.add_cog(Dev(client=client))
