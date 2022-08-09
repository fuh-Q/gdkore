from discord import ui, Interaction
from discord.app_commands import command
from discord.ext import commands

from bot import Amaze

class InviteButtons(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        self.add_item(ui.Button(
            label="bot invite",
            url="https://discord.com/api/oauth2/authorize?client_id=988862592468521031&permissions=604490816&scope=bot%20applications.commands"
        ))
        self.add_item(ui.Button(
            label="support invite",
            url="https://discord.gg/gKEKpyXeEB"
        ))


class Misc(commands.Cog):
    def __init__(self, client: Amaze) -> None:
        self.client = client
    
    @command(name="invite")
    async def invite(self, interaction: Interaction):
        """
        invite links
        """
        
        await interaction.response.send_message(
            view=InviteButtons(), ephemeral=True
        )

async def setup(client: Amaze):
    await client.add_cog(Misc(client=client))
