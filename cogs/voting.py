from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands
from discord.app_commands import command

from aiohttp import web
from topgg.webhook import WebhookManager
from topgg.types import BotVoteData

from utils import PrintColours

if TYPE_CHECKING:
    from discord import Interaction

    from bot import GClass

R = PrintColours.RED
G = PrintColours.GREEN
W = PrintColours.WHITE
P = PrintColours.PURPLE


class Voting(commands.Cog):
    def __init__(self, client: GClass) -> None:
        self.client = client

        self.client.topgg_wh = WebhookManager(client)
        self.client.topgg_wh.webserver.router.add_post(
            "/dbl", handler=self.on_topgg_vote
        )
        self.client.topgg_wh.run(1337)

    async def on_topgg_vote(self, request: web.Request):
        auth = request.headers.get("Authorization", "")
        data: BotVoteData = await request.json()
        if auth == self.client.topgg_auth and int(data["bot"]) == self.client.user.id:
            return web.Response(status=200, text="OK")

        return web.Response(status=401, text="nope fuck off")

    async def cog_unload(self) -> None:
        await self.client.topgg_wh.close()

    @command(name="vote")
    async def vote(self, interaction: Interaction):
        """
        ur cool if you vote (no pressure haha)
        """

        await interaction.response.send_message(
            f"[vote on top.gg](https://top.gg/bot/{self.client.user.id}/vote)", ephemeral=True
        )


async def setup(client: GClass):
    await client.add_cog(Voting(client=client))
