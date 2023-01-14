from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
import json



class General(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        #獲得蛋糕的冷卻
        self.cake_cooldown = 20
        self.last_cake_time = {}


    @app_commands.command(name = "info", description = "關於Natalie...")
    async def info(self,interaction):
        #讀取檔案
        with open("data/data.json","r") as f:
            data = json.load(f)
        userid = str(interaction.user.id)

        #蛋糕查詢
        if "cake" in data[userid]:
            cake = data[userid]["cake"]
        else:
            data[userid]["cake"] = 0
            cake = data[userid]["cake"]
            with open("data/data.json","w") as f:
                json.dump(data,f)

        description = """
        你好!我是Natalie!
        你可以在這裡查看個人資料及指令表。
        """
        message = Embed(title="我是Natalie!",description=description,color=common.bot_color)
        message.add_field(name="個人資料",value=f"你有{cake}塊{self.bot.get_emoji(common.cake_emoji_id)}",inline=False)
        message.add_field(
            name="指令表",
            value='''
            /info -- 查看指令表及個人資料
            ''',
            inline=False)
        await interaction.response.send_message(embed=message)

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
        with open("data/data.json","r") as f:
            data = json.load(f)

        if str(member.id) not in data:
            data[str(member.id)] = {"cake": 0}

        with open("data/data.json","w") as f:
            json.dump(data,f)

    @commands.Cog.listener()
    async def on_message(self,message):
        if not message.author.bot:
            memberid = message.author.id
            now = message.created_at
            # 如果成員還沒有獲得過蛋糕，或者已經過了冷卻時間
            if memberid not in self.last_cake_time or now - self.last_cake_time[memberid] > self.cake_cooldown:
                data = common.dataload()
                data[str(memberid)]["cake"] += 1
                common.datawrite(data)
                # 更新最後一次獲得蛋糕的時間
                self.last_cake_time[memberid] = now


async def setup(client:commands.Bot):
    await client.add_cog(General(client))