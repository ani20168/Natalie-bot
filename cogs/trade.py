from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime,timezone,timedelta
import re



class Trade(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client

    #Nitro Booster 每月可以兌換一次稱號
    @app_commands.command(name = "redeem_member_role", description = "兌換自訂稱號(每月一次)")
    @app_commands.describe(rolename="你想要兌換的稱號名",colorhex="顏色色碼，6位數HEX格式(EX:FFFFFF = 白色，000000 = 黑色")
    async def redeem_member_role(self,interaction,rolename: str,colorhex: str):
        if any(role.id == 623486844394536961 or 419185995078959104 for role in interaction.user.roles):
            #色碼防呆
            if not re.match("^[0-9a-fA-F]{6}$", colorhex):
                await interaction.response.send_message(embed=Embed(
                title="兌換自訂稱號",
                description="兌換失敗:色碼格式錯誤，請輸入6位數HEX格式色碼。\n請參考:https://www.ebaomonthly.com/window/photo/lesson/colorList.htm",
                color=common.bot_error_color))
                return
            colorhex = int("0x"+colorhex,16)

            now = datetime.now()
            data = common.dataload()
            memberid = str(interaction.user.id)
            if "redeem member role interval" in data[memberid]:
                last_redeem = datetime.strptime(data[memberid]['redeem member role interval'], '%Y-%m-%d %H:%M')
                #如果有資料，則進行天數比對
                if now - last_redeem >=timedelta(minutes=3):
                    data[memberid]['redeem member role interval'] = now.strftime('%Y-%m-%d %H:%M')
                else:
                    #不符合資格(尚在兌換冷卻期)
                    await interaction.response.send_message(embed=Embed(title="兌換自訂稱號",description="兌換失敗:你每個月只能兌換一次。",color=common.bot_error_color))
                    return

            #如果沒有資料
            else:
                data[memberid]['redeem member role interval'] = now.strftime('%Y-%m-%d %H:%M')
            #添加身分組
            await interaction.guild.create_role(name=rolename,color=colorhex,reason="Nitro Booster兌換每月自訂稱號")
            await interaction.response.send_message(embed=Embed(title="兌換自訂稱號",description=f"兌換成功!你現在擁有***{rolename}***稱號。",color=common.bot_color))
            common.datawrite(data)
            


async def setup(client:commands.Bot):
    await client.add_cog(Trade(client))