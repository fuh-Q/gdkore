from __future__ import annotations

from typing import TYPE_CHECKING, List

import discord
from discord import Interaction
from discord.ext import commands
from discord.app_commands import command

from aiohttp import web
from topgg.webhook import WebhookManager

from cogs.mazes import InventoryEntry
from utils import BotEmojis

if TYPE_CHECKING:
    from bot import Amaze


class Voting(commands.Cog):
    def __init__(self, client: Amaze) -> None:
        self.client = client
        
        self.client.topgg_wh = WebhookManager(client)
        self.client.topgg_wh.run(1337)
        self.client.topgg_wh.webserver.router.add_post(
            "/dbl", handler=self.on_topgg_vote
        )
    
    async def on_topgg_vote(self, request: web.Request):
        auth = request.headers.get("Authorization", "")
        if auth == self.client.topgg_auth:
            print(await request.json())
            return web.Response(status=200, text="OK")
        
        return web.Response(status="401", text="Yeah fuck off you sussy baka")

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
