import datetime

import discord
from discord.commands import ApplicationContext, slash_command

from bot import BanBattler
from config.utils import *


class InviteButtons(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.children[0].custom_id = None
        self.children[1].custom_id = None
        self.children[
            0
        ].url = "https://discord.com/api/oauth2/authorize?client_id=859104775429947432&permissions=268954836&scope=bot%20applications.commands"
        self.children[1].url = "https://discord.gg/6jC54cRRrm"
        self.stop()

    @discord.ui.button(label="Bot Invite", style=discord.ButtonStyle.url)
    async def bot_invite(
        self, button: discord.Button, interaction: discord.Interaction
    ):
        """Button for bot invite"""
        self.stop()

    @discord.ui.button(label="Bot Support", style=discord.ButtonStyle.url)
    async def bot_support(
        self, button: discord.Button, interaction: discord.Interaction
    ):
        """Button for bot support"""
        self.stop()


class Utility(BattlerCog):
    def __init__(self, client: BanBattler):
        self.client = client
        self.description = "Commands related to the bot itself"
        self.emoji = "🛠️"

    @BattlerCog.listener()
    async def on_ready(self):
        print("Utility cog loaded")

    @slash_command(name="ping", description="Check the bot's latency")
    async def ping(self, ctx: ApplicationContext):
        delta_uptime = datetime.datetime.utcnow() - self.client.uptime
        hours, remainder = divmod(int(delta_uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        await ctx.respond(
            content="\n".join(
                [
                    f"Latency: `{round(self.client.latency * 1000)}ms`",
                    f"Uptime: **{days}** days, **{hours}** hours, **{minutes}** minutes, **{seconds}** seconds",
                ]
            ),
            ephemeral=True,
        )

    @slash_command(name="invite", description="Invite the bot")
    async def invite(self, ctx: ApplicationContext):
        embed = discord.Embed(
            title="Invite links",
            description="\n".join(
                [
                    f"[`Invite`]({get_invite_link(self.client, permissions=268954836)})",
                    f"[`Invite (as admin)`]({get_invite_link(self.client, permissions=8)})",
                    f"[`S0uport server`](https://discord.gg/6jC54cRRrm)",
                ]
            ),
            color=self.client.color,
        )
        embed.set_footer(text="If you ended up adding me, thanks!")
        await ctx.respond(embed=embed, view=InviteButtons(), ephemeral=True)
        return


def setup(client: BanBattler):
    client.add_cog(Utility(client=client))
