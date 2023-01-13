import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
import asyncio



class Startup(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client


    @commands.Cog.listener()
    async def on_guild_join(self,guild):
        await self.bot.get_channel(common.admin_log_channel).send('cog的on_ready測試')
        await self.testloop()

async def testloop(self):
    await self.bot.get_channel(common.admin_log_channel).send('cog的loop測試')
    await asyncio.sleep(10)

        

async def setup(client:commands.Bot):
    await client.add_cog(Startup(client))