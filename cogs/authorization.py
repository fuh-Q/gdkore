from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from discord.app_commands import command

from utils import BotColours, Confirm, is_logged_in

if TYPE_CHECKING:
    from bot import GClass

    from discord import Interaction


class Authorization(commands.Cog):
    LINK_EXPIRY = 300

    def __init__(self, client: GClass):
        self.client = client

    @command(name="login")
    async def login_url(self, interaction: Interaction):
        """
        get a login link to authorize with google
        """

        def run_google(): # all of the google libs are sync
            return self.client.google_flow.authorization_url(
                access_type="offline",
                include_granted_scopes="false",
            )

        await interaction.response.defer(ephemeral=True)

        q = """SELECT * FROM authorized
                WHERE user_id = $1
            """
        if await self.client.db.fetchrow(q, interaction.user.id):
            return await interaction.followup.send(
                f"hey, it looks like you've already authorized. " \
                f"if you want to logout, just use </logout:{self.client.LOGOUT_CMD_ID}>",
                ephemeral=True
            )

        MESSAGE = "\N{WAVING HAND SIGN} hey! please go to [this link](%s) " \
                 f"to authorize with google, the link will expire " \
                 f"**<t:{int(time.time() + self.LINK_EXPIRY)}:R>**"

        url, state = await asyncio.to_thread(run_google)

        await interaction.followup.send(
            MESSAGE % url, ephemeral=True
        )

        await self.client.redis.set(state, interaction.user.id, self.LINK_EXPIRY)

    @command(name="logout")
    @is_logged_in()
    async def gc_logout(self, interaction: Interaction):
        """logout of gclass"""

        view = Confirm(interaction.user)
        embed = discord.Embed(
            title="confirm logout",
            description="you will no longer be able to use our commands " \
                        "while signed out. proceed?" \
                        "\n\n**note that all of your configured webhooks " \
                        "will stop working once you logout**",
            colour=BotColours.red
        )
        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )
        view.original_message = await interaction.original_response()

        expired = await view.wait()
        if expired:
            return await interaction.edit_original_response(view=view)

        await view.interaction.response.edit_message(view=view)
        if not view.choice:
            return await interaction.followup.send(
                "phew, dodged a bullet there", ephemeral=True
            )

        await self.client.remove_access(interaction.user.id)
        await interaction.followup.send(
            "successfully logged out", ephemeral=True
        )


async def setup(client: GClass):
    await client.add_cog(Authorization(client=client))
