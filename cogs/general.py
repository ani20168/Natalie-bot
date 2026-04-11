from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
from dateutil.parser import parse
import json
import discord
import time
import random
from typing import Optional
from collections import deque
import asyncio


class RedPacketSession:
    def __init__(self, creator_id: int, total_budget: int, people: int, amounts: list[int], ends_at: datetime):
        self.creator_id = creator_id
        self.total_budget = total_budget
        self.people = people
        self.remaining_amounts: deque[int] = deque(amounts)
        self.claimed_order: list[tuple[int, str, int]] = []
        self.claimed_user_ids: set[int] = set()
        self.lock = asyncio.Lock()
        self.ended = False
        self.ends_at = ends_at
        self.announce_message: discord.Message | None = None


class RedPacketGrabView(discord.ui.View):
    def __init__(self, cog: "General", session: RedPacketSession):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.session = session
        self.add_item(RedPacketGrabButton())

    def finish_grab_button(self, label: str) -> None:
        for child in self.children:
            if isinstance(child, RedPacketGrabButton):
                child.label = label
                child.disabled = True
                return

    async def on_timeout(self) -> None:
        message = self.session.announce_message
        if message is None:
            return
        await self.cog.finalize_red_packet(self.session, message, self, timed_out=True)


class RedPacketGrabButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="搶紅包!", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        view: RedPacketGrabView = self.view  # type: ignore[assignment]
        await view.cog.handle_red_packet_claim(interaction, view.session, view)


class General(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        #獲得蛋糕的冷卻
        self.cake_cooldown = timedelta(seconds=20)
        self.last_cake_time = {}
        self.member_invoice_time = {} 
        self.last_three_messages_info = {}
        self.color_dict = { #一般的顏色身分組
            "紅色":{"需求等級":10,"role_id":623544449280114716},
            "棕色":{"需求等級":10,"role_id":623544701840261122},
            "暗紫":{"需求等級":10,"role_id":623544702981111808},
            "橙色":{"需求等級":10,"role_id":623544707519348757},
            "黃色":{"需求等級":10,"role_id":623547225129091094},
            "暗藍":{"需求等級":10,"role_id":623547226387513345},
            "綠松石":{"需求等級":10,"role_id":623548440210702395},
            "黑色":{"需求等級":10,"role_id":675586536808382495},
            "白色":{"需求等級":10,"role_id":675586754710994964},
            "常春藤綠":{"需求等級":10,"role_id":675587892600504342},
            "緋紅":{"需求等級":10,"role_id":675592036555948052},
            "紫色":{"需求等級":10,"role_id":675592363372183607},
            "淺紫紅":{"需求等級":20,"role_id":623544703517851655},
            "粉紅色":{"需求等級":20,"role_id":623544704696320010},
            "粉玫瑰紅":{"需求等級":20,"role_id":623544705367670795},
            "薰衣草":{"需求等級":20,"role_id":623544706218852374},
            "巧克力":{"需求等級":20,"role_id":623544706583887881},
            "原木色":{"需求等級":20,"role_id":623544708366598164},
            "粉木瓜橙":{"需求等級":20,"role_id":623547224307138582},
            "天藍色":{"需求等級":20,"role_id":623547226911932442},
            "淡藍綠":{"需求等級":20,"role_id":623548441187844136},
            "香檳黃":{"需求等級":20,"role_id":675590265372934165},
            "紫丁香色":{"需求等級":20,"role_id":675591514482540594},
            "珊瑚紅":{"需求等級":20,"role_id":675593108569849856},
            "桃色":{"需求等級":20,"role_id":921046788385943572},
        }
        self.animation_color_dict = { #動態身分組
            "全息":{"role_id":1384483657301098506},
            "杏仁白":{"role_id":1384498130665476107},
            "櫻桃紅":{"role_id":1384498051791585280},
            "霧玫瑰":{"role_id":1384911899702857838},
            "矢車菊藍":{"role_id":1384920066859995277},
            "印度紅":{"role_id":1387017589418496092},
            "青瓷綠":{"role_id":1390282584361144330},
            "李紫":{"role_id":1395357795213250642},
            "亮粉紅":{"role_id":1395359026879004744},
            "動態淺紫紅":{"role_id":1422416437036711976},
        }

    @staticmethod
    def compute_red_packet_amounts(total: int, people: int) -> list[int]:
        """依規則切分紅包金額（整數蛋糕），回傳長度為 people 的清單，加總為 total。"""
        if people < 1 or people > 15:
            raise ValueError("人數需在 1～15 之間")
        if total < 1:
            raise ValueError("總金額須為正整數")
        if people == 1:
            return [total]
        if people == 2:
            if total < 2:
                raise ValueError("兩人紅包時總金額至少為 2")
            cut = random.randint(1, total - 1)
            parts = [cut, total - cut]
            random.shuffle(parts)
            return parts
        if total < people:
            raise ValueError(f"總金額至少需等於人數（每人至少 1 塊{common.cake_emoji}）")
        cuts = sorted(random.sample(range(1, total), people - 1))
        positions = [0] + cuts + [total]
        parts = [positions[index + 1] - positions[index] for index in range(people)]
        random.shuffle(parts)
        return parts

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
            cake_emoji = self.bot.get_emoji(common.cake_emoji_id)
            
            general_commands_list = [
                "/info 查看指令表及個人資料",
                f"/eat 餵食Natalie一些{cake_emoji} (1 cake = 1 exp)",
                f"/cake_give 給予他人{cake_emoji}",
                "/mining_info 挖礦小遊戲資訊",
                "/blackjack 21點遊戲",
                "/poker 撲克牌比大小",
                "/poker_statistics 撲克牌比大小個人統計",
                "/squid_rps 魷魚遊戲猜拳",
                "/check_sevencolor_restday 確認七色有沒有休假",
                "/set_color 更換ID的顏色(靜態)",
                "/set_animation_color 更換ID的顏色(動態)",
                "/red_packet 搶紅包（蛋糕）"
            ]
            #如果等級>=5 且沒有在 抽獎仔/VIP 身分內，則顯示指令
            if userlevel.level >= 5 and all(role.id not in [621764669929160715, 605730134531637249] for role in interaction.user.roles):
                general_commands_list.append("/giveaway_join 加入抽獎頻道")
            
            general_commands_list = "\n".join(general_commands_list)
            message.add_field(name="指令表",value=general_commands_list,inline=False)
            message.add_field(
                name="排行榜",
                value=f'/level_leaderboard 等級排行榜\n/voice_leaderboard 語音活躍排行榜\n/blackjack_leaderboard 21點勝率排行榜\n/squid_rps_leaderboard 魷魚猜拳勝率排行榜\n/cake_leaderboard 蛋糕排行榜',
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


        # ===== 1) 前 10 名排行榜（自動補齊） =====
        lines: list[str] = []
        shown = 0
        for rank, (uid, udata) in enumerate(sorted_data, start=1):
            # 嘗試用快取；失敗再 API 抓
            user_obj = self.bot.get_user(int(uid))
            if user_obj is None:
                try:
                    user_obj = await self.bot.fetch_user(int(uid))
                except:  # 帳號刪除或抓不到
                    continue  # 跳過並往後補人數

            lines.append(
                f"{rank}. {user_obj.display_name} "
                f"-- 等級:**{udata['level']}** 經驗值:**{udata['level_exp']}**"
            )
            shown += 1
            if shown >= 10:
                break  # 已補齊 10 筆

        message = "\n".join(lines)

        # ===== 2) 呼叫者自己的排名 =====
        for rank, (uid, udata) in enumerate(sorted_data, start=1):
            if uid == userid:
                message += (
                    f"\n\n你的排名為 **{rank}**，"
                    f"等級:**{udata['level']}** 經驗值:**{udata['level_exp']}**"
                )
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

    @app_commands.command(name="cake_leaderboard", description="蛋糕排行榜")
    async def cake_leaderboard(self, interaction):
        data = common.dataload()
        # 排除沒有cake資料或蛋糕數為0的用戶
        sorted_data = sorted(
            [(userid, userdata) for userid, userdata in data.items() 
            if isinstance(userdata, dict) and 'cake' in userdata and userdata['cake'] > 0], 
            key=lambda x: x[1]['cake'], 
            reverse=True
        )

        cake_emoji = common.cake_emoji  # 取出表情方便用

        embed = Embed(title="蛋糕排行榜", color=common.bot_color)
        leaderboard_message = f"妹妹群中 {cake_emoji} 最多的用戶：\n"

        # 顯示排名榜前10名
        for i, (userid, user_data) in enumerate(sorted_data[:10]):
            user = self.bot.get_user(int(userid))
            username = user.display_name if user else f"User({userid})"
            leaderboard_message += f"{i+1}. {username} {cake_emoji} 數:**{user_data['cake']}**\n"
        embed.description = leaderboard_message

        # 找自己的排名
        user_id = str(interaction.user.id)
        self_rank = None
        for idx, (userid, user_data) in enumerate(sorted_data):
            if userid == user_id:
                self_rank = idx + 1
                break

        if self_rank:
            embed.add_field(
                name="你的排名",
                value=f"你目前排名: **{self_rank}**  持有{cake_emoji}: **{data[user_id]['cake']}**",
                inline=False
            )
        else:
            embed.add_field(
                name="你的排名",
                value=f"你目前沒有 {cake_emoji}，快去賺取 {cake_emoji} 吧！",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

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

    @app_commands.command(description = "設置掛機斷連的觸發時間點(僅供部分會員使用)")
    @app_commands.rename(timeset = "觸發時間")
    @app_commands.describe(timeset = "何時觸發掛機斷連?範圍為15至60分鐘")
    async def afkdisconnect_trigger(self, interaction, timeset:int):
        userid = str(interaction.user.id)
        whitelist = [
            # "410847926236086272", #ANI
            "587934995063111681" #xu6
        ]
        if userid not in whitelist:
            await interaction.response.send_message(embed=Embed(title="權限不足",description="你無法使用這個指令!\n此指令僅供白名單使用。",color=common.bot_error_color), ephemeral=True)
            return

        if timeset < 15 or timeset > 60:
            await interaction.response.send_message(embed=Embed(title="設置失敗",description="時間範圍僅能選擇15~60分鐘!",color=common.bot_error_color), ephemeral=True)
            return

        async with common.jsonio_lock:
            data = common.dataload()
            data[userid]["afkdisconnect_trigger"] = timeset
            common.datawrite(data)

        admin_channel = self.bot.get_channel(common.admin_log_channel)
        await admin_channel.send(f"掛機斷連設置已經被變更! 對象:<@{userid}> 觸發時間: {timeset}分鐘")
        await interaction.response.send_message(embed=Embed(title="掛機斷連設置",description=f"設定完成! 觸發時間: {timeset}分鐘",color=common.bot_color), ephemeral=True)

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
        app_commands.Choice(name="桃色 LV20", value="桃色"),
        ])
    async def set_color(self, interaction, colorchoice:app_commands.Choice[str]):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            userlevel = common.LevelSystem().read_info(userid)

        user_roles = interaction.user.roles

        if any(role.name == colorchoice.value for role in user_roles):
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"你目前的顏色已經是 <@&{self.color_dict[colorchoice.value]['role_id']}> 了!",color=common.bot_error_color))
            return

        #只有靜態身分組才會看等級
        if colorchoice.value in self.color_dict and userlevel.level < self.color_dict[colorchoice.value]['需求等級']:
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"等級不足! <@&{self.color_dict[colorchoice.value]['role_id']}> 需要**{self.color_dict[colorchoice.value]['需求等級']}**等，你目前只有**{userlevel.level}**等。",color=common.bot_error_color))
            return

        for role in user_roles:
            #移除舊的靜態顏色身分組
            for color, attributes in self.color_dict.items():
                if role.id == attributes["role_id"]:
                    await interaction.user.remove_roles(role,reason="移除舊的顏色身分組")
                    break
            #移除舊的動態顏色身分組
            for color, attributes in self.animation_color_dict.items():
                if role.id == attributes["role_id"]:
                    await interaction.user.remove_roles(role,reason="移除舊的動態顏色身分組")
                    break
        
        if colorchoice.value in self.color_dict:
            await interaction.user.add_roles(interaction.guild.get_role(self.color_dict[colorchoice.value]['role_id']),reason="更換顏色身分組")
            await interaction.response.send_message(embed=Embed(title="設置顏色身分組",description=f"你目前的顏色變更為...<@&{self.color_dict[colorchoice.value]['role_id']}>!",color=common.bot_color))

    @app_commands.command(name = "set_animation_color",description="更換ID的顏色")
    @app_commands.describe(colorchoice="要更換的暱稱顏色")
    @app_commands.rename(colorchoice="選擇動態顏色")
    @app_commands.choices(colorchoice=[
        app_commands.Choice(name="★全息", value="全息"),
        app_commands.Choice(name="★【漸層】杏仁白", value="杏仁白"),
        app_commands.Choice(name="★【漸層】櫻桃紅", value="櫻桃紅"),
        app_commands.Choice(name="★【漸層】霧玫瑰", value="霧玫瑰"),
        app_commands.Choice(name="★【漸層】矢車菊藍", value="矢車菊藍"),
        app_commands.Choice(name="★【漸層】印度紅", value="印度紅"),
        app_commands.Choice(name="★【漸層】青瓷綠", value="青瓷綠"),
        app_commands.Choice(name="★【漸層】李紫", value="李紫"),
        app_commands.Choice(name="★【漸層】亮粉紅", value="亮粉紅"),
        app_commands.Choice(name="★【漸層】動態淺紫紅", value="動態淺紫紅"),
        ])
    async def set_animation_color(self, interaction, colorchoice:app_commands.Choice[str]):
        animation_whitelist = [
            "823967449149603861", #小八
            "277828424872230912", #七色
            "1190971324647092237", #泥巴
            "543126405978783765", #一ㄈ
            "399210985304489985", #小Q
            "472308372616773632", #tako
            "587934995063111681", #xu6
        ] #放白名單會員的ID字串
        userid = str(interaction.user.id)

        user_roles = interaction.user.roles

        if any(role.name == colorchoice.value for role in user_roles):
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"你目前的顏色已經是 <@&{self.color_dict[colorchoice.value]['role_id']}> 了!",color=common.bot_error_color))
            return

        #沒在白名單的
        if colorchoice.value in self.animation_color_dict and userid not in animation_whitelist:
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"你當前無法使用 <@&{self.animation_color_dict[colorchoice.value]['role_id']}> !\n動態身分組使用權可以在 #拍賣所 獲得!",color=common.bot_error_color))
            return

        for role in user_roles:
            #移除舊的靜態顏色身分組
            for color, attributes in self.color_dict.items():
                if role.id == attributes["role_id"]:
                    await interaction.user.remove_roles(role,reason="移除舊的顏色身分組")
                    break
            #移除舊的動態顏色身分組
            for color, attributes in self.animation_color_dict.items():
                if role.id == attributes["role_id"]:
                    await interaction.user.remove_roles(role,reason="移除舊的動態顏色身分組")
                    break
        
        if colorchoice.value in self.animation_color_dict:
            await interaction.user.add_roles(interaction.guild.get_role(self.animation_color_dict[colorchoice.value]['role_id']),reason="更換顏色身分組")
            await interaction.response.send_message(embed=Embed(title="設置動態顏色身分組",description=f"你目前的動態顏色變更為...<@&{self.animation_color_dict[colorchoice.value]['role_id']}>!",color=common.bot_color))

    def build_red_packet_embed(self, session: RedPacketSession) -> Embed:
        cake_e = common.cake_emoji
        end_line = discord.utils.format_dt(session.ends_at.astimezone(timezone(timedelta(hours=8))), style="F")
        if session.claimed_order:
            claim_lines = "\n".join(f"**{name}** — {amount} 塊{cake_e}" for _, name, amount in session.claimed_order)
        else:
            claim_lines = "尚無"
        remaining = len(session.remaining_amounts)
        embed = Embed(title="🧧 搶紅包", description=f"發包者：<@{session.creator_id}>", color=0xE74C3C)
        embed.add_field(name="結束時間", value=f"{end_line} (UTC+8)", inline=False)
        embed.add_field(name="人數", value=f"**{session.people}** 人", inline=True)
        embed.add_field(name="總金額", value=f"**{session.total_budget}** 塊{cake_e}", inline=True)
        embed.add_field(name="已領取紅包的人", value=claim_lines, inline=False)
        embed.set_footer(text=f"剩餘份數：{remaining}／{session.people}" + (" ｜已結束" if session.ended else ""))
        return embed

    async def handle_red_packet_claim(self, interaction: discord.Interaction, session: RedPacketSession, view: RedPacketGrabView) -> None:
        if interaction.guild is None or interaction.guild.id != common.fake_sister_server_id:
            await interaction.response.send_message(embed=Embed(title="搶紅包", description="僅能在妹妹群使用。", color=common.bot_error_color), ephemeral=True)
            return
        uid = interaction.user.id
        async with session.lock:
            ended = session.ended
            expired = datetime.now(timezone.utc) >= session.ends_at
        if ended:
            await interaction.response.send_message(embed=Embed(title="搶紅包", description="這個紅包已經結束了。", color=common.bot_error_color), ephemeral=True)
            return
        if expired:
            await self.finalize_red_packet(session, interaction.message, view, timed_out=True, interaction=interaction)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="這個紅包已經過期了。", color=common.bot_error_color), ephemeral=True)
            return
        async with session.lock:
            if uid == session.creator_id:
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="不能領取自己發的紅包。", color=common.bot_error_color), ephemeral=True)
                return
            if uid in session.claimed_user_ids:
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="你已經領過這個紅包了。", color=common.bot_error_color), ephemeral=True)
                return
            if not session.remaining_amounts:
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="紅包已經被搶完了。", color=common.bot_error_color), ephemeral=True)
                return
            amount = session.remaining_amounts.popleft()
            display_name = interaction.user.display_name
            session.claimed_user_ids.add(uid)
            session.claimed_order.append((uid, display_name, amount))
            done_all = len(session.remaining_amounts) == 0
        async with common.jsonio_lock:
            data = common.dataload()
            rid = str(uid)
            data.setdefault(rid, {"cake": 0})
            data[rid]["cake"] += amount
            common.datawrite(data)
        embed = self.build_red_packet_embed(session)
        if done_all:
            await self.finalize_red_packet(session, interaction.message, view, timed_out=False, interaction=interaction)
            await interaction.followup.send(embed=Embed(title="搶紅包", description=f"你搶到了 **{amount}** 塊{common.cake_emoji}！", color=common.bot_color), ephemeral=True)
            return
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(embed=Embed(title="搶紅包", description=f"你搶到了 **{amount}** 塊{common.cake_emoji}！", color=common.bot_color), ephemeral=True)

    async def finalize_red_packet(self, session: RedPacketSession, message: discord.Message, view: RedPacketGrabView, *, timed_out: bool = False, interaction: discord.Interaction | None = None) -> None:
        async with session.lock:
            if session.ended:
                already_ended = True
            else:
                already_ended = False
                session.ended = True
                refund = session.total_budget - sum(part[2] for part in session.claimed_order)
        if already_ended:
            if interaction is not None and not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=Embed(title="搶紅包", description="這個紅包已經結束了。", color=common.bot_error_color),
                    ephemeral=True,
                )
            return
        async with common.jsonio_lock:
            data = common.dataload()
            oid = str(session.creator_id)
            data.setdefault(oid, {"cake": 0})
            data[oid]["cake"] += refund
            common.datawrite(data)
        finish_label = "紅包已過期" if timed_out else "紅包已被搶完"
        view.finish_grab_button(finish_label)
        embed = self.build_red_packet_embed(session)
        try:
            if interaction is not None:
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await message.edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

    class RedPacketChannelView(discord.ui.View):
        def __init__(self, parent_cog: "General"):
            super().__init__(timeout=300.0)
            self.parent_cog = parent_cog

        @discord.ui.select(
            cls=discord.ui.ChannelSelect,
            placeholder="選擇頻道（#大廳／#機器人指令區）",
            channel_types=[discord.ChannelType.text],
        )
        async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect) -> None:
            channel = select.values[0]
            if channel.id not in common.red_packet_allowed_channel_ids:
                await interaction.response.send_message(
                    embed=Embed(title="搶紅包", description="只能選擇 **#大廳**、**#機器人指令區** 文字頻道。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            modal = General.RedPacketModal(self.parent_cog, channel.id)
            await interaction.response.send_modal(modal)

        async def on_timeout(self) -> None:
            self.stop()

    class RedPacketModal(discord.ui.Modal, title="搶紅包設定"):
        people_field = discord.ui.TextInput(label="人數 (1～15)", placeholder="要發給幾個人", required=True, max_length=2)
        total_field = discord.ui.TextInput(label="總金額 (蛋糕)", placeholder="整數，未搶完會退回剩餘", required=True, max_length=12)

        def __init__(self, parent_cog: "General", channel_id: int):
            super().__init__()
            self.parent_cog = parent_cog
            self.channel_id = channel_id

        async def on_submit(self, interaction: discord.Interaction) -> None:
            if interaction.guild is None or interaction.guild.id != common.fake_sister_server_id:
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="僅能在妹妹群使用。", color=common.bot_error_color), ephemeral=True)
                return
            try:
                people = int(self.people_field.value.strip())
                total = int(self.total_field.value.strip())
            except ValueError:
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="人數與總金額請輸入正整數。", color=common.bot_error_color), ephemeral=True)
                return
            try:
                amounts = self.parent_cog.compute_red_packet_amounts(total, people)
            except ValueError as error:
                await interaction.response.send_message(embed=Embed(title="搶紅包", description=str(error), color=common.bot_error_color), ephemeral=True)
                return
            creator_id = interaction.user.id
            async with common.jsonio_lock:
                data = common.dataload()
                oid = str(creator_id)
                data.setdefault(oid, {"cake": 0})
                if data[oid]["cake"] < total:
                    await interaction.response.send_message(
                        embed=Embed(title="搶紅包", description=f"蛋糕不足，你目前有 **{data[oid]['cake']}** 塊{common.cake_emoji}。", color=common.bot_error_color),
                        ephemeral=True,
                    )
                    return
                data[oid]["cake"] -= total
                common.datawrite(data)
            ends_at = datetime.now(timezone.utc) + timedelta(minutes=5)
            session = RedPacketSession(creator_id, total, people, amounts, ends_at)
            channel = interaction.guild.get_channel(self.channel_id)
            if channel is None or not isinstance(channel, discord.TextChannel):
                async with common.jsonio_lock:
                    data = common.dataload()
                    data[str(creator_id)]["cake"] += total
                    common.datawrite(data)
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="找不到指定的文字頻道，已退回蛋糕。", color=common.bot_error_color), ephemeral=True)
                return
            view = RedPacketGrabView(self.parent_cog, session)
            embed = self.parent_cog.build_red_packet_embed(session)
            await interaction.response.defer(ephemeral=True)
            try:
                msg = await channel.send(embed=embed, view=view)
            except discord.HTTPException:
                async with common.jsonio_lock:
                    data = common.dataload()
                    data[str(creator_id)]["cake"] += total
                    common.datawrite(data)
                await interaction.followup.send(
                    embed=Embed(title="搶紅包", description="無法在該頻道發送紅包訊息，已退回蛋糕。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            session.announce_message = msg
            await interaction.followup.send(
                embed=Embed(title="搶紅包", description=f"已發佈至 {channel.mention}，時長 **5 分鐘**。", color=common.bot_color),
                ephemeral=True,
            )

    @app_commands.command(name="red_packet", description="搶紅包：在 #大廳／#機器人指令區 發放蛋糕紅包")
    async def red_packet(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != common.fake_sister_server_id:
            await interaction.response.send_message(embed=Embed(title="搶紅包", description="此指令僅能在「偽造妹妹」伺服器使用。", color=common.bot_error_color), ephemeral=True)
            return
        view = General.RedPacketChannelView(self)
        embed = Embed(title="搶紅包", description="請先選擇要發佈紅包的文字頻道（**#大廳**、**#機器人指令區**），接著設定人數與總金額。\n時長固定 **5 分鐘**；未搶完的蛋糕會退回給你。", color=common.bot_color)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self,member, before, after):
        if member.guild.id != 419108485435883531: return #如果語音事件不在妹妹群內則略過(例如在測試群進語音之類的)
        #進入語音頻道
        if after.channel and not before.channel:
            self.member_invoice_time[str(member.id)] = time.time()
            embed = Embed(title="", description=f"{member.display_name} 進入了 {after.channel.name} 語音頻道", color=common.bot_color)
            embed.set_author(name=f"{member.global_name}", icon_url=member.avatar)
            embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
            await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

        #離開語音頻道
        if before.channel and not after.channel:
            embed = Embed(title="", description=f"{member.display_name} 離開了 {before.channel.name} 語音頻道", color=common.bot_color)
            invoice_time = time.time() - self.member_invoice_time.get(str(member.id),60)
            if invoice_time  < 10:
                embed = Embed(title="", description=f"{member.display_name} 離開了 {before.channel.name} 語音頻道 (在{invoice_time:.2f}秒內進出)", color=0xEAC100)
            self.member_invoice_time.pop(str(member.id),None)
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
                #如果除了自己外房間還有其他人，則檢查進出時間
                if len(before.channel.members) >= 2:
                    invoice_time = time.time() - self.member_invoice_time.get(str(member.id),60)
                    if invoice_time  < 10:
                        embed = Embed(title="", description=f"{member.display_name} 從 {before.channel.name} 移動到 {after.channel.name} 頻道 (在{invoice_time:.2f}秒內切換頻道)", color=0xEAC100)
                self.member_invoice_time[str(member.id)] = time.time()
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
        if message.author.bot:
            return

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

        #oh土豆的偵測
        await self.oh_totato_detect(message)
        #放假抱怨偵測
        await self.restday_complain_detect(message)
        #好想睡覺偵測
        await self.want_to_sleep_detect(message)
        #想當大俠偵測
        await self.want_play_wwm_detect(message)

        #紀錄最新的3筆訊息(用於機器人偵測)
        message_info = {
            "channel_id": message.channel.id,
            "message_id": message.id,
            "message_time": now
        }
        if memberid not in self.last_three_messages_info:
            self.last_three_messages_info[memberid] = deque(maxlen=3)
        self.last_three_messages_info[memberid].append(message_info)

        #檢查機器人行為
        if len(self.last_three_messages_info[memberid]) == 3:
            messages = list(self.last_three_messages_info[memberid])
            oldest_time = messages[0]['message_time']
            newest_time = messages[2]['message_time']
            time_difference = (newest_time - oldest_time).total_seconds()
            #最舊跟最新的訊息如果不超過3秒，而且都在不同頻道，就是異常
            if time_difference <= 3:
                channel_ids = {msg['channel_id'] for msg in messages}
                if len(channel_ids) == 3:  # Check if all channel IDs are unique
                    # Log the potential bot activity
                    member = message.author
                    await self.mute_permanent(member)
                    block_embed = Embed(title="Bot Detection",description="你在「偽造妹妹」的伺服器，發送訊息的行為異常，為了保護社群成員的帳號安全，我們已將你永久禁言，並刪除最近的訊息。\n如果你有任何問題，請向ANI(ani20168)回報。",color=common.bot_error_color)
                    block_embed.set_footer(text="Natalie 機器人防護系統")
                    await member.send(embed=block_embed)
                    admin_channel = self.bot.get_channel(common.admin_log_channel)
                    await admin_channel.send(f"偵測到機器人行為，使用者ID:<@{memberid}>")
                    asyncio.create_task(self.delete_recent_messages(member))

    async def oh_totato_detect(self, message:discord.Message):
        """
        偵測oh~關鍵字並讓bot回應土豆
        """
        if message.content != "oh~": return
        await message.channel.send("土豆")

    async def want_to_sleep_detect(self, message:discord.Message):
        """
        偵測"好想睡覺"關鍵字並讓bot回應派大星的圖
        """
        if message.content not in ["好想睡覺","想睡覺了"]: return
        #如果傳訊息的是這些人，則發送另一張圖(看看現在都幾點了)
        if message.author.id in [587934995063111681]:
            await message.channel.send("https://i.meee.com.tw/t7DJZXv.png")
            return
        await message.channel.send("https://i.meee.com.tw/GHTzB8m.jpg")

    async def restday_complain_detect(self, message:discord.Message):
        """
        偵測"好想放假"或"想放假了"關鍵字並根據今天的星期回應圖片
        """
        if message.content == "好想放假" or message.content == "想放假了":
            weekday = datetime.now().weekday()  # 0: Monday, 6: Sunday
            weekday_url_map = {
                0: 'https://thumbor.4gamers.com.tw/YyXxQ71ug_5LkjjKm7zSOavPjAg=/adaptive-fit-in/1200x1200/filters:no_upscale():extract_cover():format(jpeg):quality(85)/https%3A%2F%2Fugc-media.4gamers.com.tw%2Fpuku-prod-zh%2Fanonymous-story%2F75919057-ef63-443a-ae83-f951b7747ba1.jpg',  # 星期一
                1: 'https://megapx-assets.dcard.tw/images/395cc8dc-0ea1-4414-b662-cf035ba1a9d4/640.webp',  # 星期二
                2: 'https://i.imgur.com/hQ5TYGC.jpeg',  # 星期三
                3: 'https://megapx-assets.dcard.tw/images/272898db-892d-48d1-95dc-79ccc1800a4a/1280.jpeg',  # 星期四
                4: 'https://i.ytimg.com/vi/QM6uCrDYaiM/maxresdefault.jpg',  # 星期五
                5: 'https://i.imgur.com/v001EcH.jpeg',  # 星期六
                6: 'https://megapx-assets.dcard.tw/images/ea2dcbc5-4090-4184-83f1-6e6a3bfbd894/1280.jpeg',  # 星期日
            }
            url = weekday_url_map.get(weekday)
            if url:
                await message.channel.send(url)

    async def want_play_wwm_detect(self, message:discord.Message):
        """
        偵測"想當大俠"關鍵字並讓bot回應wwm的圖
        """
        if "想當大俠" not in message.content: return
        await message.channel.send("https://cdn.discordapp.com/attachments/419108485435883533/1465181393486090334/image.png?ex=697ec381&is=697d7201&hm=005b855bc1db5a156696345d6262aef9f120a3dd7f8fdda66bcb0c09ba996876")

    async def mute_permanent(self, member:discord.Member):
        mute_role = member.guild.get_role(563285841384833024)
        await member.add_roles(mute_role,reason="發送訊息的行為異常。永久禁言")

    async def delete_recent_messages(self, member:discord.Member):
        """
        刪除該用戶最近1分鐘內的所有訊息
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        deleted_count = 0
        
        # 遍歷伺服器所有文字頻道
        for channel in member.guild.text_channels:
            try:
                # 查詢該頻道中最近1分鐘的歷史訊息（限制100條，對於1分鐘內應該足夠）
                async for message in channel.history(limit=100, after=cutoff_time):
                    # 檢查訊息是否在1分鐘內且為該用戶發送
                    if message.author.id == member.id and message.created_at >= cutoff_time:
                        try:
                            await message.delete()
                            deleted_count += 1
                        except discord.NotFound:
                            pass  # 訊息已被刪除
                        except discord.Forbidden:
                            print(f"Do not have permissions to delete message in {channel.name}.")
                        except discord.HTTPException as e:
                            print(f"Failed to delete message in {channel.name}: {e}")
            except discord.Forbidden:
                print(f"Do not have permissions to read history in {channel.name}.")
            except Exception as e:
                print(f"Error processing channel {channel.name}: {e}")
        
        if deleted_count > 0:
            await self.bot.get_channel(common.admin_log_channel).send(f"[Bot Detection] 刪除 {member.display_name} 最近一分鐘內的{deleted_count} 筆訊息")


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