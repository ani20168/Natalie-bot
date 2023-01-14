from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime,timezone,timedelta



class Trade(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client

    #Nitro Booster 每月可以兌換一次稱號
    @app_commands.command(name = "redeem member role", description = "兌換自訂稱號(每月一次)")
    @app_commands.describe(rolename="你想要兌換的稱號名",colorhex="顏色色碼，6位數HEX格式(EX:FFFFFF = 白色，000000 = 黑色")
    async def redeem_member_role(self,interaction,rolename: str,colorhex: str):
        if any(roleid == 623486844394536961 or 419185995078959104 for roleid in interaction.member.roles.id):
            now = datetime.now
            data = common.dataload()
            


async def setup(client:commands.Bot):
    await client.add_cog(Trade(client))