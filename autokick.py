import asyncio
import traceback
from fuzzy_match import match
import re

from typing import Optional

import discord
from discord.ext import commands

from autokick_bot import AutokickBot
from config.utils import BattlerCog

def is_staff():
    async def check(ctx: commands.Context):
        if ctx.author.id == 596481615253733408:
            return True
        
        if (
            ("administrator", True) in list(ctx.author.guild_permissions)
            or ("manage_guild", True) in list(ctx.author.guild_permissions)
        ):
            return True
        
        client: AutokickBot = ctx.bot
        
        if (
            client.get_guild(client.config["main_guild"]).get_role(client.config["staff_role"])
            in ctx.author.roles
        ):
            return True
        
        return False
    
    return commands.check(check)

class Autokick(BattlerCog):
    def __init__(self, client) -> None:
        self.client: AutokickBot = client
        self.emoji = ""
    
    def cog_unload(self):
        self.kick_task.cancel()
        return
    
    async def autokick_task(self):
        try:
            while True:
                try:
                    main_guild: discord.Guild = self.client.get_guild(self.client.config["main_guild"])
                    wait_interval: float = self.client.config["wait_interval"]
                    verified_role: discord.Role = main_guild.get_role(self.client.config["verified_role"])
                    whitelisted_role: discord.Role = main_guild.get_role(self.client.config["whitelisted_role"])
                except Exception:
                    await asyncio.sleep(self.client.config["wait_interval"])
                    continue
                await asyncio.sleep(wait_interval)
                
                for m in main_guild.members:
                    if whitelisted_role in m.roles:
                        continue
                    
                    if verified_role not in m.roles:
                        print("brrrrrr")
                        try:
                            await m.kick(reason=f"{str(m)} is not verified.")
                        except discord.Forbidden:
                            continue
                        await asyncio.sleep(0.5)
        
        except asyncio.CancelledError:
            return
    
    def convert_time(self, time: str) -> float:
        """
        1m30s -> 90.0
        """
        
        number = r"(?:[0-9]+(?:\.[0-9])*)"
        units = ["w", "d", "h", "m", "s"]
        TIME_REGEX = rf"({number}\s*(?:{'|'.join(units)})\s*)"
        
        matches = re.findall(TIME_REGEX, time, flags=re.I)
        for match in matches:
            re.sub(r"\s", "", match, flags=re.I)
        
        if not matches or len("".join(matches)) != len(re.sub(r"\s", "", time, flags=re.I)):
            raise ValueError
        
        unit_converts = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
            "w": 604800,
        }
        
        total = sum([float(t[:-1]) * unit_converts[t[-1]] for t in matches])
        
        return total
    
    async def find_role(self, ctx: commands.Context, search: str) -> Optional[discord.Role]:
        try:
            role: Optional[discord.Role] = ctx.guild.get_role(int(search))
        
        except ValueError:
            pass
        
        else:
            return role
        
        try:
            role = await commands.RoleConverter().convert(ctx, search)
        
        except commands.BadArgument:
            pass
        
        else:
            return role
        
        role = match.extractOne(search, [r for r in ctx.guild.roles if r.position != 0], score_cutoff=0.2)
        if not role:
            return
        
        return role[0]
    
    @commands.Cog.listener()
    async def on_ready(self):
        print("Autokick cog loaded")
        self.kick_task = self.client.loop.create_task(self.autokick_task())
    
    @commands.group(name="config", invoke_without_command=True, case_insensitive=True)
    @is_staff()
    async def _config(self, ctx: commands.Context):
        await ctx.send(self.client.config)
    
    @_config.command(name="waitinterval", aliases=["interval"])
    @is_staff()
    async def _wait_interval(self, ctx: commands.Context, time_arg: str):
        try:
            time: float = self.convert_time(time_arg)
        except ValueError:
            return await ctx.reply(content="Couldn't convert your time. Valid units are [`w`, `d`, `h`, `m`, `s`]")
        
        else:
            if time < 600.0:
                return await ctx.reply(
                    content="Please enter a time above 10 minutes, this to to ensure we don't hit any"
                            "ratelimits with Discord, as well as to allow time for the previous iteration"
                            "to finish its job"
                )
            
            update = {"wait_interval": time}
            await self.client.config_db.update_one({}, {"$set": update}, upsert=True)
            self.client.config.update(update)
            return await ctx.reply(content=f"Set the wait interval for autokicking to {time}")
    
    @_config.command(name="mainguild", aliases=["guild"])
    @commands.is_owner()
    async def _main_guild(self, ctx: commands.Context, id: int):
        guild = self.client.get_guild(id)
        if not guild:
            return await ctx.reply(content="Guild not found")
        
        update = {"main_guild": id}
        await self.client.config_db.update_one({}, {"$set": update}, upsert=True)
        self.client.config.update(update)
    
    @_config.command(name="verifiedrole", aliases=["vrole"])
    @is_staff()
    async def _verified_role(self, ctx: commands.Context, role_search: str):
        role = await self.find_role(ctx, role_search)
        if not role:
            return await ctx.reply(content="Couldn't find a role by that query")
        
        else:
            allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)
            
            update = {"verified_role": role.id}
            await self.client.config_db.update_one({}, {"$set": update}, upsert=True)
            self.client.config.update(update)
            return await ctx.reply(content=f"Set the verified role to {role.mention}", allowed_mentions=allowed_mentions)

def setup(client: AutokickBot):
    client.add_cog(Autokick(client=client))
