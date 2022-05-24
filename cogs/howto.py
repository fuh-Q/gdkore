from datetime import datetime
from random import choice

import discord
from discord import Interaction
from discord.app_commands import command
from discord.ext import commands

from bot import NotGDKID
from config.utils import Botcolours, BotEmojis

avatars = [
    "https://cdn.discordapp.com/avatars/596481615253733408/742f6979fe30ab201350bf99dafd2624.png?size=4096",
    "https://cdn.discordapp.com/avatars/865596669999054910/5f55d7e0003edaa83f9fd6801f887ccd.png?size=4096",
    "https://cdn.discordapp.com/avatars/930701221424164905/b9e644732993f675c3636636da1bfb89.png?size=4096",
    "https://cdn.discordapp.com/avatars/859104775429947432/c55ae057136a15df6bf17f2c1fd4b5a2.png?size=4096",
]


class HowTo(commands.GroupCog, name="howto"):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

        super().__init__()

    @command(name="2048")
    async def howto2048(self, interaction: Interaction):
        """2048 game guide"""

        info_embed = (
            discord.Embed(
                description="""
                **▫️ How to Play 2048**
                
                Click the controls {0} {1} {2} {3} to move the tiles around
                Each move will shift **all tiles** in that direction (wherever possible).
                
                When two tiles of the same value move into each other,
                they merge into one and their values are added together.
                
                Your job is to get to the **2048** {4} tile (if you're playing a 4x4 grid)
                *The winning tile on a 3x3 grid is **1024*** {5},
                *and **32** {6} if you're playing on a 2x2 grid*
                
                Each move spawns in a new tile to the board, highlighted 
                in green {7} for visibility. Once your board fills up with no more 
                possible moves, **you *__lose__. {8}***
                """.format(
                    BotEmojis.ARROW_LEFT,
                    BotEmojis.ARROW_UP,
                    BotEmojis.ARROW_DOWN,
                    BotEmojis.ARROW_RIGHT,
                    BotEmojis.GUIDE_2048_ICON,
                    BotEmojis.GUIDE_1024_ICON,
                    BotEmojis.GUIDE_32_ICON,
                    "🟩",
                    "💀",
                ),
                colour=Botcolours.yellow,
                timestamp=datetime.now(),
            )
            .set_author(
                name=interaction.client.user.name,
                url="https://levelskip.com/puzzle/How-to-play-2048",
                icon_url=choice(avatars),
            )
            .set_thumbnail(url="https://www.gamebrew.org/images/6/64/2048_Screenshot.png")
            .set_footer(text="\u200b", icon_url=choice(avatars))
        )

        return await interaction.response.send_message(embed=info_embed, ephemeral=True)

    @command(name="connect4")
    async def howtoconnect4(self, interaction: Interaction):
        """connect 4 game guide"""

        info_embed = (
            discord.Embed(
                description="""
                **▫️ How to Play Connect 4**
                
                Click the arrows {0} {1} {2} {3} to move the pointer
                To drop the piece in the selected column, click the drop {4} button
                
                The goal is to get 4 pieces of your colour {5} / {6} in a row
                This "in a row" can be vertically, horizontally, or diagonally
                
                If the entire board fills up with no victor, the game is a tie
                """.format(
                    BotEmojis.C4_RED_LEFTER,
                    BotEmojis.C4_YELLOW_LEFT,
                    BotEmojis.C4_RED_RIGHT,
                    BotEmojis.C4_YELLOW_RIGHTER,
                    BotEmojis.C4_RED_DROP,
                    BotEmojis.C4_RED,
                    BotEmojis.C4_YELLOW,
                ),
                colour=Botcolours.yellow,
                timestamp=datetime.now(),
            )
            .set_author(
                name=interaction.client.user.name,
                url="https://rulesofplaying.com/connect-4-rules/",
                icon_url=choice(avatars),
            )
            .set_thumbnail(
                url="https://cdn.discordapp.com/attachments/749892811905564677/978511031468949504/unknown.png"
            )
            .set_footer(text="\u200b", icon_url=choice(avatars))
        )

        return await interaction.response.send_message(embed=info_embed, ephemeral=True)

    @command(name="checkers")
    async def howtocheckers(self, interaction: Interaction):
        """checkers game guide"""

        info_embed = (
            discord.Embed(
                description="""
                **▫️ How to Play Checkers**
                
                Use the select menu to pick a piece {0} / {1}
                The board is in a grid, with the *letter* of the piece's coordinates being 
                the *column*, and the **number** being the **row** of the piece
                
                For example, `B5` - **Second** *column*, **fifth** *row* on the board.
                
                All pieces move diagonally. To start, you can only move
                in one direction going up or down.
                
                Once you reach the end row for the direction you're going,
                that piece gets promoted to a king piece   {2} `->` {3}
                A king piece can move in all directions granted nothing is blocking its way.
                
                **The goal of Checkers** is __to jump all of your opponent's pieces__. 
                If an opponent piece is in the way, and no other piece or side boundary is behind it, it can be jumped.
                """.format(
                    BotEmojis.CHECKERS_RED,
                    BotEmojis.CHECKERS_BLUE,
                    BotEmojis.CHECKERS_BLUE,
                    BotEmojis.CHECKERS_RED_KING,
                ),
                colour=Botcolours.yellow,
                timestamp=datetime.now(),
            )
            .set_thumbnail(url="http://stockarch.com/files/10/03/checkers_board.JPG")
            .set_footer(text="\u200b", icon_url=choice(avatars))
        )

        return await interaction.response.send_message(embed=info_embed, ephemeral=True)


async def setup(client: NotGDKID):
    await client.add_cog(HowTo(client=client))
