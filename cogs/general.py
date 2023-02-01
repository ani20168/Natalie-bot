from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
import json



class General(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        #獲得蛋糕的冷卻
        self.cake_cooldown = timedelta(seconds=20)
        self.last_cake_time = {}


    @app_commands.command(name = "info", description = "關於Natalie...")
    async def info(self,interaction):
        #讀取檔案
        data = common.dataload()
        userid = str(interaction.user.id)

        #蛋糕查詢
        if "cake" in data[userid]:
            cake = data[userid]["cake"]
        else:
            data[userid]["cake"] = 0
            cake = data[userid]["cake"]
            common.datawrite(data)

        userlevel = common.LevelSystem().read_info(userid)
        description = "你好!我是Natalie!\n你可以在這裡查看個人資料及指令表。"
        message = Embed(title="我是Natalie!",description=description,color=common.bot_color)
        message.add_field(name="個人資料",value=f"等級:**{userlevel.level}**  經驗值:**{userlevel.level_exp}**/**{userlevel.level_next_exp}**\n你有**{cake}**塊{self.bot.get_emoji(common.cake_emoji_id)}",inline=False)
        message.add_field(
            name="指令表",
            value='''
            /info -- 查看指令表及個人資料
            /eat -- 餵食Natalie
            /mining_info 挖礦小遊戲資訊
            ''',
            inline=False)
        await interaction.response.send_message(embed=message)

    @app_commands.command(name = "eat", description = "餵食Natalie!")
    @app_commands.describe(eat_cake="要餵食的蛋糕數量，1蛋糕=1經驗值")
    @app_commands.rename(eat_cake="數量")
    async def eat(self,interaction,eat_cake: int):       
        if eat_cake <=0:
            await interaction.response.send_message(embed=Embed(title='餵食Natalie',description="錯誤:請輸入有效的數量",color=common.bot_error_color))
            return

        data = common.dataload()
        userid = str(interaction.user.id)
        userlevel = common.LevelSystem().read_info(userid)
        
        cake = data[userid]["cake"]

        if cake >= eat_cake:
            cake -= eat_cake
            userlevel.level_exp += eat_cake
            message = Embed(title='餵食Natalie',description=f"我吃飽啦!(獲得**{eat_cake}**點經驗值)",color=common.bot_color)
            #升級
            if userlevel.level_exp >= userlevel.level_next_exp:
                while userlevel.level_exp >= userlevel.level_next_exp:
                    userlevel.level += 1
                    userlevel.level_next_exp = userlevel.level * (userlevel.level+1)*30
                message.add_field(name="升級!",value=f"你現在{userlevel.level}等了。",inline=False)

            data[userid]["level"] = userlevel.level
            data[userid]["level_exp"] = userlevel.level_exp
            data[userid]["level_next_exp"] = userlevel.level_next_exp
            data[userid]["cake"] = cake
            common.datawrite(data)
            await interaction.response.send_message(embed=message)
        else:
            await interaction.response.send_message(embed=Embed(title='餵食Natalie',description="錯誤:蛋糕不足",color=common.bot_error_color))
            return

    @app_commands.command(name = "level_leaderboard", description = "等級排行榜")
    async def level_leaderboard(self,interaction):
        pass


    @commands.Cog.listener()
    async def on_voice_state_update(self,member, before, after):
    #進入語音頻道
        if after.channel and not before.channel:
            embed = Embed(title="", description=f"{member.display_name} 進入了 {after.channel.name} 語音頻道", color=common.bot_color)
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.avatar)
            embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
            await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

        #離開語音頻道
        if before.channel and not after.channel:
            embed = Embed(title="", description=f"{member.display_name} 離開了 {before.channel.name} 語音頻道", color=common.bot_color)
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.avatar)
            embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
            await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

        #切換語音頻道
        if before.channel != after.channel:
            if before.channel and after.channel:
                embed = Embed(title="", description=f"{member.display_name} 從 {before.channel.name} 移動到 {after.channel.name} 頻道", color=common.bot_color)
                embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.avatar)
                embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
                await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self,member):  
        data = common.dataload()

        if str(member.id) not in data:
            data[str(member.id)] = {"cake": 0}

        common.datawrite(data)

    @commands.Cog.listener()
    async def on_message(self,message):
        if not message.author.bot:
            memberid = str(message.author.id)
            now = datetime.now()
            # 如果成員還沒有獲得過蛋糕，或者已經過了冷卻時間
            if memberid not in self.last_cake_time or now - self.last_cake_time[memberid] > self.cake_cooldown:
                data = common.dataload()
                data[memberid]["cake"] += 1
                common.datawrite(data)
                # 更新最後一次獲得蛋糕的時間
                self.last_cake_time[memberid] = datetime.now()


async def setup(client:commands.Bot):
    await client.add_cog(General(client))