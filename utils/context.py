from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot import GClass
    from helper_bot import NotGDKID


class NGKContext(commands.Context[commands.Bot]):
    bot: GClass | NotGDKID

    async def try_react(self, *, emoji: str | discord.PartialEmoji):
        try:
            await self.message.add_reaction(emoji)
        except discord.HTTPException:
            pass
