import time

import discord
from discord.ext import commands

from config.json import Json


class Dev(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.emoji = "<a:gdkid:868976838112841760>"

    @commands.Cog.listener()
    async def on_ready(self):
        print("Dev cog loaded")

    @commands.command(aliases=["servers"], hidden=True, brief="Get the bot's server count")
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
        e = discord.Embed(description="❯❯ Aight brb")
        msg = await ctx.reply(embed=e)
        Json.write_json(
            {
                "id": msg.id,
                "chan_id": msg.channel.id if ctx.guild else None,
                "now": time.monotonic(),
            },
            "restart",
        )
        await self.client.close(restart=True)

    @commands.command(name="hi", brief='Say "Hi" to the bot', hidden=True)
    @commands.is_owner()
    async def hi(self, ctx: commands.Context):
        await ctx.reply("hi")


async def setup(client: commands.Bot):
    await client.add_cog(Dev(client=client))
