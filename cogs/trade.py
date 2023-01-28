import discord
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

            #ban word
            ban_word_list = ["administrator","moderator","管理員","admin","mod","ADMINISTRATOR","MODERATOR","ADMIN","MOD"]
            #如果rolename在list內，或者在妹妹群的身分組內
            if any(ban_word == rolename for ban_word in ban_word_list) or any(similar_word.name == rolename for similar_word in self.bot.get_guild(419108485435883531).roles):
                await interaction.response.send_message(embed=Embed(title="兌換自訂稱號",description="兌換失敗:與現有身分組重複或相似。",color=common.bot_error_color))
                return
                

            now = datetime.now()
            data = common.dataload()
            memberid = str(interaction.user.id)
            if "redeem member role interval" in data[memberid]:
                last_redeem = datetime.strptime(data[memberid]['redeem member role interval'], '%Y-%m-%d %H:%M')
                #如果有資料，則進行天數比對
                if now - last_redeem >=timedelta(days=30):
                    data[memberid]['redeem member role interval'] = now.strftime('%Y-%m-%d %H:%M')
                else:
                    #不符合資格(尚在兌換冷卻期)
                    remaining_time = last_redeem + timedelta(days=30) - now
                    remaining_days, remaining_seconds = divmod(remaining_time.days * 24 * 60 * 60 + remaining_time.seconds, 86400)
                    remaining_hours, remaining_seconds = divmod(remaining_seconds, 3600)
                    await interaction.response.send_message(embed=Embed(
                            title="兌換自訂稱號",
                            description=f"兌換失敗:你每個月只能兌換一次，距離下次兌換還有**{remaining_days}**天**{remaining_hours}**小時。",
                            color=common.bot_error_color))
                    return

            #如果沒有資料
            else:
                data[memberid]['redeem member role interval'] = now.strftime('%Y-%m-%d %H:%M')
            #添加身分組
            await interaction.guild.create_role(name=rolename,color=colorhex,reason="Nitro Booster兌換每月自訂稱號")
            await interaction.user.add_roles(discord.utils.get(interaction.guild.roles,name=rolename))
            await interaction.response.send_message(embed=Embed(title="兌換自訂稱號",description=f"兌換成功!你現在擁有《 **{rolename}** 》稱號。",color=common.bot_color))
            common.datawrite(data)
            
    @app_commands.command(name = "cake_give", description = "贈送蛋糕")
    @app_commands.describe(member="你想要給予的人(使用提及)",amount="給予的蛋糕數量")
    @app_commands.rename(member="@用戶",amount="數量")
    async def cake_give(self,interaction,member: discord.Member,amount: int):
        userid = str(interaction.user.id)
        user_data = common.dataload()
        if interaction.user == member:
            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:你無法贈送給自己。",color=common.bot_error_color))
            return
        if member.bot:
            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:你無法贈送給bot。",color=common.bot_error_color))
            return
        if amount <= 0:
            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:你輸入有效的數字。",color=common.bot_error_color))
            return
        if user_data[userid]["cake"] < amount:
            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description=f"錯誤:蛋糕不足，你只有**{user_data[userid]['cake']}**塊蛋糕。",color=common.bot_error_color))
            return

        user_data[userid]["cake"] -= amount
        user_data[str(member.id)]["cake"] += amount
        common.datawrite(user_data)

        await interaction.response.send_message(embed=Embed(title="給予蛋糕",description=f"你給予了**{amount}**塊蛋糕給<@{str(member.id)}>",color=common.bot_color))


async def setup(client:commands.Bot):
    await client.add_cog(Trade(client))