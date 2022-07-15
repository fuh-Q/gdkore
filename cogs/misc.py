import discord
from discord import Interaction
from discord.app_commands import command
from discord.ext import commands

from bot import Amaze

class Misc(commands.Cog):
    def __init__(self, client: Amaze) -> None:
        self.client = client
    
    @command(name="vote")
    async def vote(self, interaction: Interaction):
        """
        ur cool if you vote (no pressure haha)
        """
        
        await interaction.response.send_message(
            "[vote on top.gg](https://top.gg/bot/988862592468521031)", ephemeral=True
        )
    
    @command(name="support")
    async def support(self, interaction: Interaction):
        """
        the place to ask for help
        """
        
        await interaction.response.send_message(
            "[support server](https://discord.gg/A4fCkfc7)", ephemeral=True
        )

async def setup(client: Amaze):
    await client.add_cog(Misc(client=client))
