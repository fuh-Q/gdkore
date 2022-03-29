from discord.ext import commands

from bot import NotGDKID


class TypeRace(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Typerace cog loaded")

    @commands.command(aliases=["tr"])
    @commands.is_owner()
    async def typerace(self, ctx: commands.Context):
        """starts a typerace"""


def setup(client: NotGDKID):
    client.add_cog(TypeRace(client=client))
