from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List

import discord
from discord import Interaction
from discord.ext import commands
from discord.app_commands import command

from aiohttp import web
from topgg.webhook import WebhookManager

from cogs.mazes import Game
from utils import BotEmojis, PrintColours

if TYPE_CHECKING:
    from bot import Amaze

R = PrintColours.RED
G = PrintColours.GREEN
W = PrintColours.WHITE
P = PrintColours.PURPLE


class Voting(commands.Cog):
    def __init__(self, client: Amaze) -> None:
        self.client = client
        
        self.client.topgg_wh = WebhookManager(client)
        self.client.topgg_wh.webserver.router.add_post(
            "/dbl", handler=self.on_topgg_vote
        )
        self.client.topgg_wh.run(1337)
    
    async def on_topgg_vote(self, request: web.Request):
        auth = request.headers.get("Authorization", "")
        data = await request.json()
        if auth == self.client.topgg_auth and int(data["bot"]) == self.client.user.id:
            uid = int(data["user"])
            dashes = 35 if datetime.now().weekday() >= 5 else 25
            
            if (game := self.client._mazes.get(uid, None)):
                game.max_dash_count += dashes
                game.update_max_dash_button()
                
                await game.original_message.edit(view=game)
            else:
                await Game.update_dashes(self.client.db, uid, dashes, add=True)
            
            user = await self.client.fetch_user(uid)
            weekend = "!" if dashes == 25 else "on a weekend!"
            e = discord.Embed(
                title="thanks for voting!",
                description=f"you got {BotEmojis.MAZE_DASH_SYMBOL} **{dashes}** dashes "
                            f"for voting on top.gg {weekend}"
            )
            try:
                await user.send(embed=e)
            except discord.HTTPException:
                self.client.logger.warning(
                    f"Could not DM {G}{user.name}{R}#{user.discriminator}{W} "
                    f"[{P}{user.id}{W}] whilst giving vote rewards"
                )
            
            return web.Response(status=200, text="OK")
        
        return web.Response(status="401", text="Yeah fuck off you sussy baka")
    
    async def cog_unload(self) -> None:
        await self.client.topgg_wh.close()

    @command(name="vote")
    async def vote(self, interaction: Interaction):
        """
        ur cool if you vote (no pressure haha)
        """
        
        await interaction.response.send_message(
            "[vote on top.gg](https://top.gg/bot/988862592468521031)", ephemeral=True
        )


async def setup(client: Amaze):
    await client.add_cog(Voting(client=client))
