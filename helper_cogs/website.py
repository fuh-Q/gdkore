from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, List, TYPE_CHECKING

import discord
from discord.ext import commands
from discord.app_commands import ContextMenu

from utils import BotEmojis, is_owner

if TYPE_CHECKING:
    from discord import Interaction

    from helper_bot import NotGDKID
    from utils import NGKContext

Date = Annotated[datetime, lambda x: datetime.fromisoformat(x)] | None


class Website(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

        self.add_note_app_cmd = ContextMenu(name="add note", callback=self.add_note_msg)
        self.client.tree.add_command(self.add_note_app_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command("add note")

    @staticmethod
    async def _convert_attachments(attachments: List[discord.Attachment]) -> str:
        ret = ""
        for attachment in attachments:
            if attachment.content_type and attachment.content_type.startswith("image"):
                ret += f"\n{attachment.url}"
            else:
                ret += (await attachment.read()).decode("utf-8")

        return ret

    async def _add_note(self, content: str, attachments: List[discord.Attachment]) -> str | None:
        if attachments:
            content += await self._convert_attachments(attachments)

        if not content:
            return

        q = "INSERT INTO notes (timestamp, note) VALUES ($1, $2)"
        return await self.client.web_db.execute(q, datetime.now(tz=timezone.utc), content)

    async def _edit_note(self, id: int | None, content: str, attachments: List[discord.Attachment]) -> str:
        if attachments:
            content += await self._convert_attachments(attachments)

        q = "UPDATE notes SET note = $2 WHERE id = COALESCE($1, (SELECT MAX(id) FROM notes))"
        return await self.client.web_db.execute(q, id, content)

    async def _delete_note(self, id: int | None) -> str:
        q = "DELETE FROM notes WHERE id = $1 COALESCE($1, (SELECT MAX(id) FROM notes))"
        return await self.client.web_db.execute(q, id)

    @is_owner()
    async def add_note_msg(self, interaction: Interaction, message: discord.Message):
        await self._add_note(message.content, message.attachments)
        await interaction.response.send_message("note added", ephemeral=True, delete_after=3)

    @commands.command(name="addnote", aliases=["an", "sn"])
    @commands.is_owner()
    async def add_note_cmd(self, ctx: NGKContext, *, note_content: str):
        await self._add_note(note_content, ctx.message.attachments)

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="editnote", aliases=["en"])
    @commands.is_owner()
    async def edit_note_cmd(self, ctx: NGKContext, note_id: int | None, *, note_content: str):
        status = await self._edit_note(note_id, note_content, ctx.message.attachments)
        if status[-1] == "0":
            return await ctx.reply("this note doesn't exist lol", delete_after=3)

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="deletenote", aliases=["dn"])
    @commands.is_owner()
    async def delete_note_cmd(self, ctx: NGKContext, note_id: int | None):
        status = await self._delete_note(note_id)
        if status[-1] == "0":
            return await ctx.reply("this note doesn't exist lol", delete_after=3)

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="mark", aliases=["sm"])
    @commands.is_owner()
    async def set_mark_cmd(self, ctx: NGKContext, date: Date = None, *, note: str | None = None):
        date = date or datetime.now()
        q = "INSERT INTO screamdates VALUES ($1, $2) ON CONFLICT ON CONSTRAINT screamdates_pkey DO UPDATE SET notes = $2"
        await self.client.web_db.execute(q, date, note)

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="editmark", aliases=["em"])
    @commands.is_owner()
    async def edit_mark_cmd(self, ctx: NGKContext, date: Date = None, *, note: str | None = None):
        date = date or datetime.now()

        q = """UPDATE screamdates SET notes = $4
            WHERE EXTRACT(YEAR FROM day) = $1
            AND EXTRACT(MONTH FROM day) = $2
            AND EXTRACT(DAY FROM day) = $3
        """

        status = await self.client.web_db.execute(q, date.year, date.month, date.day, note)
        if status[-1] == "0":
            return await ctx.reply("that day wasn't marked", delete_after=5)

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="deletemark", aliases=["dm"])
    @commands.is_owner()
    async def delete_mark_cmd(self, ctx: NGKContext, date: Date = None):
        date = date or datetime.now()

        q = """DELETE FROM screamdates
            WHERE EXTRACT(YEAR FROM day) = $1
            AND EXTRACT(MONTH FROM day) = $2
            AND EXTRACT(DAY FROM day) = $3
        """

        status = await self.client.web_db.execute(q, date.year, date.month, date.day)
        if status[-1] == "0":
            return await ctx.reply("that day wasn't marked", delete_after=5)

        await ctx.try_react(emoji=BotEmojis.YES)


async def setup(client: NotGDKID):
    await client.add_cog(Website(client=client))
