import discord
from discord.ext import commands
from discord.commands import (
    ApplicationContext,
    user_command
)

class Utility(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
    
    @commands.Cog.listener()
    async def on_ready(self):
        print("Utility cog loaded")
    
    @user_command(name="Invite Bot")
    async def invite_bot(self, ctx: ApplicationContext, member: discord.Member):
        if not member.bot:
            return await ctx.respond(f"{member.mention} is not a bot", ephemeral=True)
        
        url = f"https://discord.com/oauth2/authorize?client_id={member.id}&permissions=1099511627775&scope=bot%20applications.commands"
        
        return await ctx.respond(f"[Click here to invite {member.name}]({url}) (feel free to toggle the invite's permissions as needed)", ephemeral=True)

def setup(client: commands.Bot):
    client.add_cog(Utility(client))
