import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime, timezone, timedelta
import asyncio



class Startup(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.testloop.start()  

    async def cog_unload(self):
        self.testloop.cancel()
        
    @tasks.loop(seconds=10)
    async def testloop(self):
        pass
        
    @testloop.before_loop    
    async def before_testloop(self):
        await self.bot.wait_until_ready()


        

async def setup(client:commands.Bot):
    await client.add_cog(Startup(client))