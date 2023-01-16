import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime,timezone,timedelta




class Startup(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.clearstardoor.start()  
        self.userdata_initialization.start()
        self.give_cake_in_vc.start()

    #卸載cog時觸發
    async def cog_unload(self):
        self.clearstardoor.cancel()
        self.userdata_initialization.cancel()
        self.give_cake_in_vc.cancel()

        
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

    #用戶資料初始化/檢查
    @tasks.loop(seconds=5,count=1)
    async def userdata_initialization(self):
        data = common.dataload()

        for member in self.bot.get_all_members():
            if str(member.id) not in data:
                data[str(member.id)] = {"cake": 0}

        common.datawrite(data)

    #每5分鐘，有在指定的語音頻道內則給予蛋糕
    @tasks.loop(minutes=5)
    async def give_cake_in_vc(self):
        vclist = [
            419108485435883535,
            456422626567389206,
            616238868164771861,
            540856580325769226,
            540856651805360148,
            540856695992221706]
        
        data = common.dataload()

        for channelid in vclist:
            channel = self.bot.get_channel(channelid)
            for member in channel.members:
                #如果資料內有用戶ID(正常都會有)，並且非機器人
                if str(member.id) in data and member.bot == False:
                    data[str(member.id)]["cake"] += 1
                #VIP和MOD獎勵
                if str(member.id) in data and any(role.id == 419185180134080513 or 605730134531637249 for role in member.roles):
                    data[str(member.id)]["cake"] += 1
                if str(member.id) in data and member.activity:
                    if member.activity.type == discord.ActivityType.streaming:
                        data[str(member.id)]["cake"] += 1
                        await self.bot.get_channel(common.admin_log_channel).send(content=f"{member.name}直播中")

        common.datawrite(data)




    @clearstardoor.before_loop    
    async def before_clearstardoor(self):
        await self.bot.wait_until_ready()
    @userdata_initialization.before_loop    
    async def before_userdata_initialization(self):
        await self.bot.wait_until_ready()
    @give_cake_in_vc.before_loop
    async def before_give_cake_in_vc(self):
        await self.bot.wait_until_ready()
        

async def setup(client:commands.Bot):
    await client.add_cog(Startup(client))