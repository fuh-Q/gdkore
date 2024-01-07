from __future__ import annotations

import io
from PIL import Image
from typing import Tuple, TYPE_CHECKING

import discord
from discord import Attachment
from discord.app_commands import Group, describe
from discord.ext import commands

from bot import Amaze
from utils import BotEmojis

if TYPE_CHECKING:
    Interaction = discord.Interaction[Amaze]


class MazeConfig(commands.Cog):
    settings = Group(name="mazeconfig", description="configuration commands")

    def __init__(self, client: Amaze) -> None:
        self.client = client

    @staticmethod
    def hex2rgb(code: str) -> Tuple[int, ...]:
        c = code.lstrip("#")[:6]
        return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def rgb2hex(rgb: Tuple[int, int, int]) -> str:
        return "#%02x%02x%02x" % (rgb[0], rgb[1], rgb[2])

    async def set_colour(self, interaction: Interaction, colour: str, space_type: str):
        try:
            rgb = self.hex2rgb(colour)
        except ValueError:
            return await interaction.response.send_message(
                content=f"that doesnt look a valid hex {BotEmojis.HAHALOL}", ephemeral=True
            )

        q = """INSERT INTO maze_settings (user_id, {0}_colour) VALUES ($1, $2)
                ON CONFLICT ON CONSTRAINT maze_settings_pkey
                DO UPDATE SET
                    {0}_colour = $2
                WHERE excluded.user_id = $1
            """.format(
            space_type
        )

        await self.client.db.execute(q, interaction.user.id, rgb)
        await interaction.response.send_message(
            content=f"{space_type} colour set to `#{colour.lstrip('#')}` {BotEmojis.HEHEBOI}", ephemeral=True
        )

    async def reset_colour(self, interaction: Interaction, space_type: str):
        q = """UPDATE maze_settings SET
                    {0}_colour = NULL
                WHERE user_id = $1
            """.format(
            space_type
        )

        await self.client.db.execute(q, interaction.user.id)
        await interaction.response.send_message(f"reset your {space_type} colour {BotEmojis.HEHEBOI}", ephemeral=True)

    async def set_icon(self, interaction: Interaction, icon: Attachment, icon_type: str):
        if icon.size > 2_000_000 or icon.content_type not in ("image/png", "image/jpeg"):
            return await interaction.response.send_message(
                "please upload an image (png/jpg) that's under `2 MB` in size", ephemeral=True
            )

        buffer = io.BytesIO()
        await icon.save(buffer)
        img = Image.open(buffer)
        img = img.resize((37, 37))
        img.save(buffer := io.BytesIO(), "png")
        img.close()
        buffer.seek(0)

        q = """INSERT INTO maze_settings (user_id, {0}) VALUES ($1, $2)
                ON CONFLICT ON CONSTRAINT maze_settings_pkey
                DO UPDATE SET
                    {0} = $2
                WHERE excluded.user_id = $1
            """.format(
            icon_type
        )

        await self.client.db.execute(q, interaction.user.id, buffer.read())
        await interaction.response.send_message(
            f"{icon_type} icon set to [`{icon.filename}`] {BotEmojis.HEHEBOI}", ephemeral=True
        )

    async def reset_icon(self, interaction: Interaction, icon_type: str):
        q = """UPDATE maze_settings SET
                    {0} = NULL
                WHERE user_id = $1
            """.format(
            icon_type
        )

        await self.client.db.execute(q, interaction.user.id)
        return await interaction.response.send_message(f"reset your {icon_type} icon {BotEmojis.HEHEBOI}", ephemeral=True)

    @settings.command(name="background")
    @describe(colour="the background colour; format must be hex")
    async def settings_bgcolour(self, interaction: Interaction, colour: str | None):
        """
        customize your background colour; only hex is supported atm
        """

        if not colour:
            return await self.reset_colour(interaction, "bg")

        await self.set_colour(interaction, colour, "bg")

    @settings.command(name="wall")
    @describe(colour="the wall colour; format must be hex")
    async def settings_wallcolour(self, interaction: Interaction, colour: str | None):
        """
        customize your wall colour; only hex is supported atm
        """

        if not colour:
            return await self.reset_colour(interaction, "wall")

        await self.set_colour(interaction, colour, "wall")

    @settings.command(name="title")
    @describe(text="the text to set as the title caption")
    async def settings_title(self, interaction: Interaction, text: str | None):
        """
        customize the text displayed over mazes when you play
        """

        if text is None:
            q = "UPDATE maze_settings SET title = NULL WHERE user_id = $1"
            await self.client.db.execute(q, interaction.user.id)
            return await interaction.response.send_message(f"title removed {BotEmojis.HEHEBOI}", ephemeral=True)

        if len(text) > 32:
            return await interaction.response.send_message(
                "please keep the text under 32 characters, thanks :)", ephemeral=True
            )

        q = """INSERT INTO maze_settings (user_id, title) VALUES ($1, $2)
                ON CONFLICT ON CONSTRAINT maze_settings_pkey
                DO UPDATE SET
                    title = $2
                WHERE excluded.user_id = $1
            """
        await self.client.db.execute(q, interaction.user.id, text)
        await interaction.response.send_message(f"title set {BotEmojis.HEHEBOI}", ephemeral=True)

    @settings.command(name="player")
    @describe(icon="the icon to set; must be a working image")
    async def settings_player(self, interaction: Interaction, icon: Attachment | None):
        """
        customize your player icon. attachment must be an image
        """

        if not icon:
            return await self.reset_icon(interaction, "player")

        await self.set_icon(interaction, icon, "player")

    @settings.command(name="endzone")
    @describe(icon="the icon to set; must be a working image")
    async def settings_endzone(self, interaction: Interaction, icon: Attachment | None):
        """
        customize your endzone icon (displayed at the end of maze). attachment must be an image
        """

        if not icon:
            return await self.reset_icon(interaction, "endzone")

        await self.set_icon(interaction, icon, "endzone")

    @settings.command(name="reset")
    async def settings_reset(self, interaction: Interaction):
        """
        reset all your configurations back to default
        """

        q = """DELETE FROM maze_settings WHERE user_id = $1 RETURNING user_id"""
        found = await self.client.db.fetchval(q, interaction.user.id)
        if found:
            msg = f"your settings have been deleted {BotEmojis.HEHEBOI}"
        else:
            msg = f"you never had any customizations set {BotEmojis.HAHALOL}"

        await interaction.response.send_message(msg, ephemeral=True)

    # @command(name="forgetmydata")
    # async def forgetmydata(self, interaction: Interaction):
    #     """
    #     deletes all data the bot has stored on you
    #     """

    #     return await interaction.response.send_message("this command needs reworking", ephemeral=True)

    #     view = Confirm(interaction.user)
    #     confirm_embed = discord.Embed(
    #         title="confirm data delete",
    #         description="this will delete all of your saved games/configurations",
    #         colour=BotColours.cyan
    #     )

    #     await interaction.response.send_message(
    #         embed=confirm_embed, view=view, ephemeral=True
    #     )
    #     view.original_message = await interaction.original_response()
    #     await view.wait()
    #     await view.interaction.response.edit_message(view=view)

    #     if view.choice:
    #         await interaction.followup.send("data cleared", ephemeral=True)

    #         q = """SELECT tablename FROM pg_tables
    #                 WHERE tableowner = 'GDKID'
    #             """
    #         data = await self.client.db.fetch(q)

    #         for record in data:
    #             q = "DELETE FROM %s WHERE user_id = $1" % record[0]
    #             await self.client.db.execute(q, interaction.user.id)
    #     else:
    #         await interaction.followup.send("k nvm then", ephemeral=True)


async def setup(client: Amaze):
    await client.add_cog(MazeConfig(client=client))
