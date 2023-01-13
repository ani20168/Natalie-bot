import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime, timezone, timedelta
import asyncio




class Startup(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.clearstardoor.start()  

    #卸載cog時觸發
    async def cog_unload(self):
        self.clearstardoor.cancel()
        
    #自動鎖定過期的星門
    @tasks.loop(time=datetime.time(hour=17,tzinfo=datetime.timezone(datetime.timedelta(hours=8))))
    async def clearstardoor(self):
        list = self.bot.get_channel(1057894690478899330).threads
        await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="星門管理員",description="正在清除過期的星門...",color=common.bot_color))
        if len(list) != 0:
            for thread in list:
                if any( tag.name == "星門" for tag in thread.applied_tags):
                    await thread.edit(archived=True,locked=True,reason="自動鎖定過期的星門")
            await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="星門管理員",description=f"已鎖定{len(list)}個星門。",color=common.bot_color))
        else: 
            await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="星門管理員",description="沒有可以鎖定的星門。",color=common.bot_color))

    @clearstardoor.before_loop    
    async def before_clearstardoor(self):
        await self.bot.wait_until_ready()


        

async def setup(client:commands.Bot):
    await client.add_cog(Startup(client))