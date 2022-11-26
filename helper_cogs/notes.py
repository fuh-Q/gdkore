from __future__ import annotations

from datetime import datetime, timezone
from typing import List, TYPE_CHECKING

import discord
from discord.ext import commands
from discord.app_commands import ContextMenu

from utils import BotEmojis, is_owner

if TYPE_CHECKING:
    from discord import Interaction

    from helper_bot import NotGDKID
    from utils import NGKContext


class Notes(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

        self.add_note_app_cmd = ContextMenu(name="add note", callback=self.add_note_msg)
        self.client.tree.add_command(self.add_note_app_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command("add note")

    @staticmethod
    def _convert_attachments(attachments: List[discord.Attachment]) -> str:
        return "\n".join(f"![attachment {idx}]({attachment.url})" for idx, attachment in enumerate(attachments))

    async def _add_note(self, content: str, attachments: List[discord.Attachment]) -> None:
        if attachments:
            content += "\n" + self._convert_attachments(attachments)

        if not content:
            return

        q = "INSERT INTO notes (timestamp, note) VALUES ($1, $2)"
        await self.client.web_db.execute(q, datetime.now(tz=timezone.utc), content)

    async def _edit_note(self, id: int, content: str, attachments: List[discord.Attachment]) -> str:
        if attachments:
            content += "\n" + self._convert_attachments(attachments)

        q = "UPDATE notes SET note = $2 WHERE id = $1"
        return await self.client.web_db.execute(q, content, id)

    async def _delete_note(self, id: int) -> str:
        q = "DELETE FROM notes WHERE id = $1"
        return await self.client.web_db.execute(q, id)

    @is_owner()
    async def add_note_msg(self, interaction: Interaction, message: discord.Message):
        await interaction.response.defer(ephemeral=True)

        await self._add_note(message.content, message.attachments)
        await interaction.followup.send("note added")

    @commands.command(name="addnote", aliases=["an", "sn"])
    @commands.is_owner()
    async def add_note_cmd(self, ctx: NGKContext, *, note_content: str):
        await self._add_note(note_content, ctx.message.attachments)

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="editnote", aliases=["en"])
    @commands.is_owner()
    async def edit_note_cmd(self, ctx: NGKContext, note_id: int, *, note_content: str):
        status = await self._edit_note(note_id, note_content, ctx.message.attachments)
        if status[-1] == "0":
            return await ctx.reply("this note doesn't exist lol")

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="deletenote", aliases=["dn"])
    @commands.is_owner()
    async def delete_note_cmd(self, ctx: NGKContext, note_id: int):
        status = await self._delete_note(note_id)
        if status[-1] == "0":
            return await ctx.reply("this note doesn't exist lol")

        await ctx.try_react(emoji=BotEmojis.YES)


async def setup(client: NotGDKID):
    await client.add_cog(Notes(client=client))
