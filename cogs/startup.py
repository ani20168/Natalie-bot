import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime,timezone,timedelta
import asyncio




class Startup(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.clearstardoor.start()  

    #卸載cog時觸發
    async def cog_unload(self):
        self.clearstardoor.cancel()
        
    #自動鎖定過期的星門
    @tasks.loop(hours=1)
    async def clearstardoor(self):
        nowtime = datetime.now(timezone(timedelta(hours=8)))
        if nowtime.hour == 0:
            list = self.bot.get_channel(1057894690478899330).threads           
            if len(list) != 0:
                for thread in list:
                    if any( tag.name == "星門" for tag in thread.applied_tags):
                        await thread.edit(archived=True,locked=True,reason="自動鎖定過期的星門")

    @clearstardoor.before_loop    
    async def before_clearstardoor(self):
        await self.bot.wait_until_ready()


        

async def setup(client:commands.Bot):
    await client.add_cog(Startup(client))