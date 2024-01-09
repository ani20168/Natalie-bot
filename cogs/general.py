from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
from dateutil.parser import parse
import json
import discord
import time
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
            message = Embed(title="我是Natalie!",description="你好!我是Natalie!\n你可以在這裡查看個人資料及指令表。",color=common.bot_color)
            message.add_field(name="個人資料",value=f"等級:**{userlevel.level}**  經驗值:**{userlevel.level_exp}**/**{userlevel.level_next_exp}**\n你有**{cake}**塊{self.bot.get_emoji(common.cake_emoji_id)}",inline=False)
            
            general_commands_list=f'/info 查看指令表及個人資料\n/eat 餵食Natalie\n/cake_give 給予他人{self.bot.get_emoji(common.cake_emoji_id)}\n/mining_info 挖礦小遊戲資訊\n/blackjack 21點遊戲\n/poll 簡單的投票功能\n/check_sevencolor_restday 確認七色有沒有休假'
            #如果等級>=5 且沒有在 抽獎仔/VIP 身分內，則顯示指令
            if userlevel.level >= 5 and all(role.id not in [621764669929160715, 605730134531637249] for role in interaction.user.roles):
                general_commands_list += "\n/giveaway_join 加入抽獎頻道"
            
            message.add_field(name="指令表",value=general_commands_list,inline=False)
            message.add_field(
                name="排行榜",
                value=f'/level_leaderboard 等級排行榜\n/voice_leaderboard 語音活躍排行榜\n/blackjack_leaderboard 21點勝率排行榜',
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
            message += (f"%d.%s -- 等級:**%d** 經驗值:**%d**\n" % (i + 1, user_object.display_name, user_data['level'], user_data['level_exp']))


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
            leaderboard_message += f"{i+1}.{user.display_name} 語音分鐘數:**{user_data['voice_active_minutes']}**\n"
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
            option_message += f"{reactions[i]} {option}\n\n"

        message = Embed(title=title,description=option_message,color=common.bot_color)

        # 發送投票訊息
        await interaction.response.send_message(embed=message)

        poll_message = await interaction.original_response()
        # 添加反應符號
        for reaction in reactions:
            await poll_message.add_reaction(reaction)


    @app_commands.command(name = "giveaway_join", description = "加入抽獎頻道")
    async def giveaway_join(self,interaction):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            userlevel = common.LevelSystem().read_info(userid)
        if userlevel.level >= 5 and all(role.id not in [621764669929160715, 605730134531637249] for role in interaction.user.roles):
            await interaction.user.add_roles(interaction.guild.get_role(621764669929160715))
            await interaction.response.send_message(embed=Embed(title="加入抽獎頻道",description="歡迎進入giveaway頻道!",color=common.bot_color))
        else:
            await interaction.response.send_message(embed=Embed(title="加入抽獎頻道",description="你無法使用這個指令!\n你已經具備抽獎仔身分，或者等級不足以進入。",color=common.bot_error_color))

    @app_commands.command(name = "check_sevencolor_restday", description = "確認七色珀的休假日")
    @app_commands.rename(date='日期')
    @app_commands.describe(date='輸入日期以查看當天是否休假，或著留空來查看他的下一次休假日期')
    async def check_sevencolor_restday(self,interaction,date:Optional[str] = None):
        # 設定起始工作日
        start_working_date = datetime(2023, 12, 28)

        # 工作和休息的週期（四天工作，兩天休息）
        work_days = 4
        rest_days = 2
        cycle_days = work_days + rest_days

        # 相對日期描述
        relative_dates = {
            -1: "昨天",
            0: "今天",
            1: "明天",
            2: "後天"
        }

        # 使用系統當前日期
        current_date = datetime.now()

        #加入表情
        cry_emoji = self.bot.get_emoji(1054249722304540713)
        happy_emoji = self.bot.get_emoji(652707676081487895)

        #footer
        with_date_note = '提示:不輸入日期可以查看最近一次的休假週期'
        withnot_date_note = '提示:輸入日期可以查看當天有沒有放假'

        try:
            if date:
                # 解析輸入的日期
                check_date = parse(date)
                total_days = (check_date - start_working_date).days
                position_in_cycle = total_days % cycle_days

                # 判斷是否為休息日
                if position_in_cycle >= work_days:
                    await interaction.response.send_message(embed=Embed(title="查詢休假日...",description=f"七色在這天放假!{happy_emoji} ({check_date.date()})",color=common.bot_color).set_footer(text=with_date_note))
                else:
                    await interaction.response.send_message(embed=Embed(title="查詢休假日...",description=f"七色在這天沒有放假...{cry_emoji} ({check_date.date()})",color=common.bot_color).set_footer(text=with_date_note))
            else:
                # 查找下一個休息日的週期
                days_since_start = (current_date - start_working_date).days
                current_position_in_cycle = days_since_start % cycle_days

                # 如果當前日期在工作日內
                if current_position_in_cycle < work_days:
                    days_to_next_rest_day = work_days - current_position_in_cycle
                    rest_day_1 = current_date + timedelta(days=days_to_next_rest_day)
                    rest_day_2 = rest_day_1 + timedelta(days=1)
                else:
                    # 如果當前日期已經在休息日
                    days_to_last_rest_day = current_position_in_cycle - work_days
                    rest_day_1 = current_date - timedelta(days=days_to_last_rest_day)
                    rest_day_2 = rest_day_1 + timedelta(days=1)

                # 決定如何顯示休息日日期
                today = current_date.date()
                date_diff_1 = (rest_day_1.date() - today).days
                date_diff_2 = (rest_day_2.date() - today).days

                rest_day_str_1 = relative_dates.get(date_diff_1, rest_day_1.strftime("%Y/%m/%d"))
                rest_day_str_2 = relative_dates.get(date_diff_2, rest_day_2.strftime("%Y/%m/%d"))

                await interaction.response.send_message(embed=Embed(title="最近的休假週期...",description=f"七色在 **{rest_day_str_1}** 跟 **{rest_day_str_2}** 放假!",color=common.bot_color).set_footer(text=withnot_date_note))
        except ValueError:
            await interaction.response.send_message(embed=Embed(title="錯誤!",description="日期格式錯誤!",color=common.bot_error_color))

    @app_commands.command(name = "set_color",description="更換ID的顏色")
    @app_commands.describe(colorchoice="要更換的暱稱顏色")
    @app_commands.rename(colorchoice="選擇顏色")
    @app_commands.choices(colorchoice=[
        app_commands.Choice(name="紅色 LV10", value="紅色"),
        app_commands.Choice(name="棕色 LV10", value="棕色"),
        app_commands.Choice(name="暗紫 LV10", value="暗紫"),
        app_commands.Choice(name="橙色 LV10", value="橙色"),
        app_commands.Choice(name="黃色 LV10", value="黃色"),
        app_commands.Choice(name="暗藍 LV10", value="暗藍"),
        app_commands.Choice(name="綠松石 LV10", value="綠松石"),
        app_commands.Choice(name="黑色 LV10", value="黑色"),
        app_commands.Choice(name="白色 LV10", value="白色"),
        app_commands.Choice(name="常春藤綠 LV10", value="常春藤綠"),
        app_commands.Choice(name="緋紅 LV10", value="緋紅"),
        app_commands.Choice(name="紫色 LV10", value="紫色"),
        app_commands.Choice(name="淺紫紅 LV20", value="淺紫紅"),
        app_commands.Choice(name="粉紅色 LV20", value="粉紅色"),
        app_commands.Choice(name="粉玫瑰紅 LV20", value="粉玫瑰紅"),
        app_commands.Choice(name="薰衣草 LV20", value="薰衣草"),
        app_commands.Choice(name="巧克力 LV20", value="巧克力"),
        app_commands.Choice(name="原木色 LV20", value="原木色"),
        app_commands.Choice(name="粉木瓜橙 LV20", value="粉木瓜橙"),
        app_commands.Choice(name="天藍色 LV20", value="天藍色"),
        app_commands.Choice(name="淡藍綠 LV20", value="淡藍綠"),
        app_commands.Choice(name="香檳黃 LV20", value="香檳黃"),
        app_commands.Choice(name="紫丁香色 LV20", value="紫丁香色"),
        app_commands.Choice(name="珊瑚紅 LV20", value="珊瑚紅"),
        app_commands.Choice(name="桃色 LV20", value="桃色")
        ])
    async def set_color(self, interaction, colorchoice:app_commands.Choice[str]):
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message('開發中...稍後在回來看看。')
            return
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            userlevel = common.LevelSystem().read_info(userid)
        color_dict = {
            "紅色":{"需求等級":10,"role_id":623544449280114716},
            "棕色":{"需求等級":10,"role_id":623544701840261122},
            "暗紫":{"需求等級":10,"role_id":623544702981111808},
        }
        user_roles = interaction.user.roles

        if any(role.name == colorchoice.value for role in user_roles):
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"你目前的顏色已經是 <@&{color_dict[colorchoice.value]['role_id']}> 了!",color=common.bot_error_color))
            return

        if userlevel.level < color_dict[colorchoice.value]['需求等級']:
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"等級不足! <@&{color_dict[colorchoice.value]['role_id']}> 需要**{color_dict[colorchoice.value]['需求等級']}**等，你目前只有**{userlevel.level}**等。",color=common.bot_error_color))
            return

        for role in user_roles:
            for color, attributes in color_dict.items():
                if role.id == attributes["role_id"]:
                    await interaction.user.remove_roles(role,reason="移除舊的顏色身分組")
                    break
        
        await interaction.user.add_roles(interaction.guild.get_role(color_dict[colorchoice.value]['role_id']),reason="更換顏色身分組")
        await interaction.response.send_message(embed=Embed(title="設置顏色身分組",description=f"你目前的顏色變更為...<@&{color_dict[colorchoice.value]['role_id']}>!",color=common.bot_color))
        

    @commands.Cog.listener()
    async def on_voice_state_update(self,member, before, after):
    #進入語音頻道
        if after.channel and not before.channel:
            embed = Embed(title="", description=f"{member.display_name} 進入了 {after.channel.name} 語音頻道", color=common.bot_color)
            embed.set_author(name=f"{member.global_name}", icon_url=member.avatar)
            embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
            await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

        #離開語音頻道
        if before.channel and not after.channel:
            embed = Embed(title="", description=f"{member.display_name} 離開了 {before.channel.name} 語音頻道", color=common.bot_color)
            embed.set_author(name=f"{member.global_name}", icon_url=member.avatar)
            embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
            await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

            async with common.jsonio_lock:
                data = common.dataload()
                #清除AFK狀態
                if 'afk_start' in data[str(member.id)]:
                    del data[str(member.id)]['afk_start']
                    common.datawrite(data)

        #切換語音頻道
        if before.channel != after.channel:
            if before.channel and after.channel:
                embed = Embed(title="", description=f"{member.display_name} 從 {before.channel.name} 移動到 {after.channel.name} 頻道", color=common.bot_color)
                embed.set_author(name=f"{member.global_name}", icon_url=member.avatar)
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

    @commands.Cog.listener()
    async def on_guild_role_update(self,before,after):
        #如果Nitro booster更動
        if after.id == 623486844394536961:
            #檢查是否有新加入的booster但未進入VIP身分
            before_set = set(before.members)
            after_set = set(after.members)
            added_members = after_set - before_set
            removed_members = before_set - after_set
            vip_role = after.guild.get_role(605730134531637249)

            #新加入的Booster
            if len(added_members) >= 1:
                #如果未加入VIP身分(605730134531637249)，則加入
                async with common.jsonio_lock:  
                    data = common.dataload()
                    for member in added_members:
                        if vip_role not in member.roles:
                            await member.add_roles(vip_role,reason="新的Nitro Booster加入，賦予VIP身分組")
                            data[str(member.id)]["vip_join_time"] = datetime.now()
                    common.datawrite(data)

            # 離開的booster
            if len(removed_members) >= 1:
                async with common.jsonio_lock:
                    data = common.dataload()
                    for member in removed_members:
                        if vip_role in member.roles:
                            # 檢查是否已經是VIP身分組30天
                            vip_join_time = data[str(member.id)].get("vip_join_time", datetime.now() - timedelta(days=30))
                            if datetime.now() - vip_join_time < timedelta(days=30):
                                await member.remove_roles(vip_role, reason="Nitro Booster身分組未達30天就離開，移除VIP身分組")
                                if "vip_join_time" in data[str(member.id)]:
                                    del data[str(member.id)]["vip_join_time"]
                    common.datawrite(data)



async def setup(client:commands.Bot):
    await client.add_cog(General(client))