import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime,timezone,timedelta
import asyncio
import json




class Startup(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.clearstardoor.start()  
        self.userdata_initialization.start()

    #卸載cog時觸發
    async def cog_unload(self):
        self.clearstardoor.cancel()
        self.userdata_initialization.cancel()

        
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

    #用戶資料建檔
    @tasks.loop(seconds=5,count=1)
    async def userdata_initialization(self):
        await self.bot.get_channel(common.admin_log_channel).send("資料初始化測試訊息")
        with open("data/data.json","r") as f:
            data = json.load(f)
        for member in self.bot.get_all_members():
            if member.id not in data:
                data[member.id] = {"cake": 0}
        with open("data/data.json","w") as f:
            json.dump(data,f)



    @clearstardoor.before_loop    
    async def before_clearstardoor(self):
        await self.bot.wait_until_ready()
    @userdata_initialization.before_loop    
    async def before_userdata_initialization(self):
        await self.bot.wait_until_ready()

        

async def setup(client:commands.Bot):
    await client.add_cog(Startup(client))