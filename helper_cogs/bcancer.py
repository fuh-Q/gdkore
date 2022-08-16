from __future__ import annotations

import asyncio
import io
import random
import re
import unicodedata
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from utils import BotEmojis, Confirm

if TYPE_CHECKING:
    from helper_bot import NotGDKID


class BCancer(commands.Cog):
    CHAR = "\U0001f171"
    VOWELS = ("a", "e", "i", "o", "u", "y")
    REPLACABLES = ["c", "d", "g", "j", "k", "p", "q", "t", "v", "z"]
    
    def __init__(self, client: NotGDKID) -> None:
        self.client = client
    
    def make_nick(self, text: str):
        if "b" in text.lower():
            return re.sub(r"b|B", self.CHAR, text)
        
        def consonants():
            random.shuffle(self.REPLACABLES)
            tu = [(s.lower(), s.upper()) for s in self.REPLACABLES]
            for lower, upper in tu:
                if lower in text.lower():
                    p = rf"(?:{lower}|{upper})+"
                    found = re.search(p, text)
                    if not found:
                        continue
                    else:
                        found = found[0]
                    return text[:(idx := text.index(found))] + self.CHAR*len(found) + text[idx + len(found):]
        
        def vowels():
            for idx, char in enumerate(text):
                if char.lower() in self.VOWELS:
                    return text[:idx - 1] + self.CHAR + text[idx:]
        
        def run_tests():
            if text[0].lower() in self.VOWELS:
                return self.CHAR + text[0].lower() + text[1:]
            else:
                out = random.choices((consonants, vowels), (6, 4), k=1)[0]()
                if out:
                    return out
        
        out = run_tests()
        if out:
            return out
        
        lite_decancer = unicodedata.normalize("NFKC", text)
        lite_decancer = unicodedata.normalize("NFD", lite_decancer)
        lite_decancer = "".join(c for c in lite_decancer if re.search(r"^[\x20-\x7E]*$", c))
        if len(lite_decancer) != len(text):
            return self.CHAR
        
        new = "".join(text[index] if not char.lower() == "b" else self.CHAR for index, char in enumerate(lite_decancer))
        if self.CHAR in new:
            return new
        
        out = run_tests()
        if out:
            return out
        return self.CHAR
    
    def is_bcancered(self, member: discord.Member):
        return self.CHAR in member.display_name
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self.is_bcancered(member):
            nick = self.make_nick(member.display_name)
            await member.edit(nick=nick, reason="member 🅱️-cancer'd")
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.display_name != after.display_name:
            if not self.is_bcancered(after):
                nick = self.make_nick(after.display_name)
                await after.edit(nick=nick, reason="member 🅱️-cancer'd")
    
    @commands.command(name="bcancer")
    @commands.is_owner()
    async def bcancer(self, ctx: commands.Context, member: discord.Member):
        nick = self.make_nick(member.name)
        
        await member.edit(
            nick=nick,
            reason=f"manual 🅱️-cancer requested by {ctx.author.name}#{ctx.author.discriminator}"
        )
        
        return await ctx.message.add_reaction(BotEmojis.YES)
    
    @commands.command(name="bhoist")
    @commands.is_owner()
    async def bhoist(self, ctx: commands.Context):
        to_bcancer = [m for m in ctx.guild.members if not self.is_bcancered(m)]
        if not to_bcancer:
            return await ctx.reply(
                "theres no one to `🅱️`-cancer 🅱️reh", mention_author=True
            )
        
        base = "would you like to `🅱️`-cancer the following **`{0}`** members?"
        view = Confirm(ctx.author)
        
        try:
            cutoff = 10
            content = [
                base.format(len(to_bcancer)),
                "\u200b",
                "```py",
            ]
            if len(to_bcancer) > cutoff:
                content.append(
                    "\n".join(f"{m.name}#{m.discriminator}" for m in to_bcancer[:cutoff])
                )
                content.append(f"\n... ({len(to_bcancer) - cutoff} more)")
            else:
                content.append(
                    "\n".join(f"{m.name}#{m.discriminator}" for m in to_bcancer)
                )
            content.append("```")
            
            msg = await ctx.reply("\n".join(content), view=view, mention_author=True)
        except discord.HTTPException:
            content = base.format(len(to_bcancer)) + "\n\u200b"
            text = "\n".join(f"{m.name}#{m.discriminator}" for m in to_bcancer)
            
            msg = await ctx.reply(
                content,
                file=discord.File(io.BytesIO(text.encode("utf-8")), "names.txt"),
                view=view,
                mention_author=True
            )
        
        view.original_message = msg
        
        expired = await view.wait()
        if expired or not view.choice:
            if not view.interaction:
                await view.original_message.edit(view=view)
            else:
                await view.interaction.response.edit_message(view=view)
            return await ctx.reply("ok guess not then", mention_author=True)
        
        await view.interaction.response.edit_message(view=view)
        msg = await ctx.reply(
            f"alrighty, i should be finishing up <t:{int(time.time() + (len(to_bcancer) * 1.25))}:R>",
            mention_author=True
        )
        async with ctx.typing():
            success = fail = 0
            
            for member in to_bcancer.copy():
                nick = self.make_nick(member.name)
                try:
                    await member.edit(nick=nick)
                    success += 1
                except discord.HTTPException:
                    fail += 1
                
                to_bcancer.remove(member)
                if to_bcancer:
                    await asyncio.sleep(0.75)
        
        return await msg.reply(
            "`🅱️`-hoist completed\n\n"
            f"— {BotEmojis.YES} success `{success}`"
            f"— {BotEmojis.NO} fails `{fail}`—"
        )
        
    
async def setup(client: NotGDKID):
    await client.add_cog(BCancer(client=client))
