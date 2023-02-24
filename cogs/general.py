from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
import json
import discord
from typing import Optional



class General(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        #獲得蛋糕的冷卻
        self.cake_cooldown = timedelta(seconds=20)
        self.last_cake_time = {}


    @app_commands.command(name = "info", description = "關於Natalie...")
    async def info(self,interaction):
        async with common.jsonio_lock:
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
                value=f'''
                /info 查看指令表及個人資料
                /eat 餵食Natalie
                /cake_give 給予他人{self.bot.get_emoji(common.cake_emoji_id)}
                /mining_info 挖礦小遊戲資訊
                /level_leaderboard 等級排行榜
                /voice_leaderboard 語音活躍排行榜
                /blackjack 21點遊戲
                /blackjack_leaderboard 21點勝率排行榜
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

        async with common.jsonio_lock:
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
        userid = str(interaction.user.id)
        data = common.dataload()
        async with common.jsonio_lock:
            userlevel_info = common.LevelSystem().read_info(userid)
        # 建立排名榜的列表，以經驗值為排序準則，並倒序排列
        sorted_data = sorted([(user, user_data) for user, user_data in data.items() if isinstance(user_data, dict) and "level_exp" in user_data], key=lambda x: x[1]["level_exp"], reverse=True)


        message = ""
        # 顯示排名榜前10名
        for i, (user, user_data) in enumerate(sorted_data[:10]):
            user_object = self.bot.get_user(int(user))
            message += (f"%d.%s -- 等級:**%d** 經驗值:**%d**\n" % (i + 1, user_object.name, user_data['level'], user_data['level_exp']))


        # 找出使用指令者的排名
        for i, (user, user_data) in enumerate(sorted_data):
            if user == userid:
                message += ("\n你的排名為**%d**，等級:**%d** 經驗值:**%d**" % (i + 1, user_data['level'], user_data['level_exp']))
                break

        await interaction.response.send_message(embed=Embed(title="等級排行榜",description=message,color=common.bot_color))
        
    @app_commands.command(name = "voice_leaderboard", description = "語音活躍排行榜")
    async def voice_leaderboard(self,interaction):
        data = common.dataload()
         #如果用戶資料內有voice_active_minutes且>10分鐘
        sorted_data = sorted([(userid, userdata) for userid, userdata in data.items() if isinstance(userdata, dict) and 'voice_active_minutes' in userdata and userdata['voice_active_minutes'] > 10], key=lambda x: x[1]['voice_active_minutes'], reverse=True)
       
        message = Embed(title="語音活躍排行榜",description="",color=common.bot_color)
        leaderboard_message = "注意:需要在語音內至少10分鐘才會記錄至排行榜。\n"
        # 顯示排名榜前10名
        for i, (userid, user_data) in enumerate(sorted_data[:10]):
            user = self.bot.get_user(int(userid))
            leaderboard_message += f"{i+1}.{user.name} 語音分鐘數:**{user_data['voice_active_minutes']}**\n"
        message.description = leaderboard_message

        # 昨日排行榜
        if "yesterday_voice_leaderboard" in data:
            message.add_field(name="昨日前三名",value=data['yesterday_voice_leaderboard'],inline=False)

        await interaction.response.send_message(embed=message)

    @app_commands.command(name = "cake_add", description = "增加蛋糕")
    @app_commands.describe(member = "選擇一個成員",amount = "數量(扣除蛋糕加上負號)")
    async def cake_add(self,interaction,member: discord.Member,amount:int):
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="為用戶增加蛋糕",description="權限不足。",color=common.bot_error_color))
            return
        async with common.jsonio_lock:
            data = common.dataload()
            cake_before = data[str(member.id)]['cake']
            data[str(member.id)]['cake'] += amount
            common.datawrite(data)
            cake_emoji = self.bot.get_emoji(common.cake_emoji_id)
            await interaction.response.send_message(embed=Embed(title="為用戶增加蛋糕",description=f"<@{member.id}>資料變更...\n原始{cake_emoji}:**{cake_before}**\n增加了**{amount}**塊{cake_emoji}\n現在有**{data[str(member.id)]['cake']}**塊{cake_emoji}",color=common.bot_color))

    @app_commands.command(name = "poll", description = "投票")
    @app_commands.rename(title="標題",option1="選項1",option2="選項2",option3="選項3",option4="選項4",option5="選項5")
    async def poll(self,interaction, title: str, option1: str, option2: str, option3: Optional[str] = None,option4: Optional[str] = None,option5: Optional[str] = None):
        options = [option1, option2]
        reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']  # 1~5的數字表情符號

        # 添加選項3
        if option3:
            options.append(option3)

        # 添加選項4
        if option4:
            options.append(option4)

        # 添加選項5
        if option5:
            options.append(option5)

        # 將反應符號添加到列表
        reactions = reactions[:len(options)]

        # 建立投票訊息
        option_message = ""
        for i, option in enumerate(options):
            option_message += f"**{i+1}**:{option}\n\n"

        message = Embed(title=title,description=option_message,color=common.bot_color)

        # 發送投票訊息
        await interaction.response.send_message(embed=message)

        poll_message = await interaction.original_response()
        # 添加反應符號
        for reaction in reactions:
            await poll_message.add_reaction(reaction)

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
        async with common.jsonio_lock:
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
                async with common.jsonio_lock:
                    data = common.dataload()
                    data[memberid]["cake"] += 1
                    common.datawrite(data)
                # 更新最後一次獲得蛋糕的時間
                self.last_cake_time[memberid] = datetime.now()


async def setup(client:commands.Bot):
    await client.add_cog(General(client))