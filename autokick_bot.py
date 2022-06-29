"""

"""

import discord
from discord.ext import commands

import asyncio
import logging
import sys

from pymongo.database import Database
from pymongo.collection import Collection

from motor.motor_asyncio import AsyncIOMotorClient
from jishaku.shim.paginator_200 import PaginatorInterface

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Bot")

mongoURI = "mongodb+srv://GDKID:I2E4s678go@autokickcluster.zi9er.mongodb.net/AutokickData?retryWrites=true&w=majority"
db: Database = AsyncIOMotorClient(mongoURI)["AutokickData"]

class AutokickBot(commands.Bot):
    token = "OTQ0Njc1MTI5ODczNTMwOTYy.YhFDRg.Bogj436mSXF-9soEqtxjN4kvCG8"
    
    def __init__(self):
        intents = discord.Intents.all()
        allowed_mentions = discord.AllowedMentions().all()
        
        extensions = [
            "cogs.autokick",
            "cogs.debug",
            "cogs.dev",
            "cogs.Eval",
            "cogs.help"
        ]
        
        self.active_jishaku_paginators: list[PaginatorInterface] = []
        self.config_db: Collection = db["Config"]
        self.config = {}
        
        self.yes = "<:yes_tick:842078179833151538>"
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            allowed_mentions=allowed_mentions
        )
        
        for extension in extensions:
            self.load_extension(extension)
        
        self.loop.create_task(self.load_cache())
    
    async def load_cache(self):
        await self.get_config()
    
    async def get_config(self, **kwargs):
        update: dict = await self.config_db.find_one({})
        if not update:
            update = {
                "_id": self.user.id,
                "wait_interval": 600.0,
                "main_guild": 749892811905564672,#897226774356852867,
                "verified_role": 906643078822109196,
                "whitelisted_role": 913428896425336862,
                "staff_role": 913428896425336862
            }
            await self.config_db.insert_one(update)
            
        self.config.update(update)
    
    async def on_connect(self):
        await self.change_presence(
            status=discord.Status.idle, activity=discord.Game(name="Starting up...")
        )
    
    async def on_ready(self):
        await self.change_presence(activity=None)
        log.info(f"Logged in as: {self.user.name} : {self.user.id}\n===========================")
    
    async def start(self):
        await super().start(self.token)
    
    async def close(self, restart: bool = False):
        extensions = self.extensions.copy()
        for name in extensions.keys():
            self.unload_extension(name)
        
        for pag in self.active_jishaku_paginators:
            await pag.message.edit(view=None)
            self.active_jishaku_paginators.pop(
                self.active_jishaku_paginators.index(pag)
            )

            if self.active_jishaku_paginators:
                await asyncio.sleep(0.25)
        
        await self.config_db.delete_many({})
        await self.config_db.insert_one(self.config)

        if restart is True:
            for voice in self.voice_clients:
                try:
                    await voice.disconnect()

                except Exception:
                    continue

            if self.ws is not None and self.ws.open:
                await self.ws.close(code=1000)

            sys.exit(69)

        else:
            await super().close()

AutokickBot().run()
