import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime,timezone,timedelta
import re
from pathlib import Path
import asyncio

class Auction:
    """單一競標的執行中狀態。"""

    # -----------------------------
    # 防搶標參數 (類別層級)
    # -----------------------------
    EXTEND_THRESHOLD = 60  # 剩餘秒數 ≤ 此值時觸發延長
    EXTEND_DURATION = 30   # 每次延長的秒數

    def __init__(self, *, item: str, start_price: int, increment: int,
                 end_time: datetime, author_id: int, message: discord.Message,
                 bot: commands.Bot, start_time: datetime | None = None):
        self.item = item                        # 商品名稱
        self.start_price = start_price          # 起標價
        self.increment = increment              # 每次最小加價
        self.end_time = end_time                # 競標結束時間 (UTC)
        self.author_id = author_id              # 建立者 ID
        self.message = message                  # Discord 訊息物件 (用來更新)
        self.view: "AuctionView | None" = None  # 留存 View 物件以便後續更新
        self.bot = bot                          # Bot 實例，供後續通知使用

        # 競標狀態
        self.highest_bid = start_price - increment  # 設為 "尚未有人出價" 的前置值
        self.highest_bidder: int | None = None      # 目前最高出價者 ID
        self.bid_count: int = 0                     # 出價次數
        self.bid_history: dict[int, int] = {}       # 用戶預扣金額紀錄 {user_id: 已預扣總額}
        self.lock = asyncio.Lock()                  # 保護競態條件
        safe_name = self._safe_filename(self.item)          # ← 轉成安全檔名
        self.log_path = Path("log/bid") / f"{safe_name}_{message.id}.txt"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.start_time = start_time or datetime.now(timezone.utc)
        self.reminder_users: set[int] = set()       # 記錄希望提醒的用戶
        now = datetime.now(timezone.utc)
        self.start_event_handled: bool = self.start_time <= now
        self.reminder_notified: bool = False

    # ----------------------------------------------------
    # 工具函式
    # ----------------------------------------------------
    @property
    def started(self) -> bool:
        """判斷競標是否已經開始。"""
        return datetime.now(timezone.utc) >= self.start_time

    def time_until_start(self) -> int:
        """回傳距離開始還有幾秒 (小於 0 代表已開始)。"""
        return int((self.start_time - datetime.now(timezone.utc)).total_seconds())

    def next_price(self) -> int:
        """計算下一次出價需要的金額。"""
        return self.highest_bid + self.increment

    def remaining(self) -> int:
        """回傳剩餘秒數 (小於 0 代表已到期)。"""
        return int((self.end_time - datetime.now(timezone.utc)).total_seconds())

    def needs_extension(self) -> bool:
        """判斷是否觸發防搶標延長。"""
        return self.remaining() <= self.EXTEND_THRESHOLD

    async def reserve(self, user_id: int, amount: int):
        """預扣指定用戶的蛋糕。"""
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        spend_result = await userdata_collection.find_one_and_update(
            {"_id": str(user_id), "cake": {"$gte": amount}},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": -amount}},
            upsert=False,
            return_document=common.ReturnDocument.AFTER,
        )
        if spend_result is None:
            raise ValueError(f"{common.cake_emoji}不足")

    async def refund(self, user_id: int, amount: int):
        """退款給指定用戶。"""
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        await userdata_collection.update_one({"_id": str(user_id)}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": amount}}, upsert=True)

    async def place_bid(self, interaction: discord.Interaction):
        """處理按鈕互動產生的出價。必須於 self.lock 內呼叫。"""
        bidder_id = interaction.user.id
        if not self.started:
            raise ValueError("競標尚未開始，請稍候再出價")
        # 固定最高價者不得連續出價
        if bidder_id == self.highest_bidder:
            raise ValueError("你已是最高出價者，無法再次出價")

        next_price = self.next_price()
        previously_reserved = self.bid_history.get(bidder_id, 0)
        additional_needed = next_price - previously_reserved
        if additional_needed <= 0:
            raise ValueError("你的出價已經是目前最高價")
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        spend_result = await userdata_collection.find_one_and_update(
            {"_id": str(bidder_id), "cake": {"$gte": additional_needed}},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": -additional_needed}},
            upsert=False,
            return_document=common.ReturnDocument.AFTER,
        )
        if spend_result is None:
            raise ValueError(f"{common.cake_emoji}不足，無法出價")

        # 更新競標狀態
        self.bid_history[bidder_id] = previously_reserved + additional_needed
        self.highest_bid = next_price
        self.highest_bidder = bidder_id
        self.bid_count += 1

        # 防搶標：如剩餘時間過短則延長
        if self.needs_extension():
            self.end_time += timedelta(seconds=self.EXTEND_DURATION)

    async def write_log(self, bidder_name: str):
        """
        將成功出價寫入 log/bid/<商品名稱_訊息ID>.txt
        Args:
            bidder_name (str): Discord 的 display_name
        Returns:
            None
        """
        line = f"第{self.bid_count}次出價:{bidder_name} 出價{self.highest_bid}個蛋糕\n"
        # 用 run_in_executor 避免阻塞 event-loop
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,                      # 預設 ThreadPool
            self.log_path.open("a", encoding="utf-8").write,
            line
        )

    async def notify_reminders(self):
        """通知設定提醒的用戶競標已經開始。"""
        if not self.reminder_users or self.reminder_notified:
            return
        self.reminder_notified = True
        message = (
            f"競標 **{self.item}** 已經開始囉！\n"
            f"直接前往：{self.message.jump_url}"
        )
        for user_id in list(self.reminder_users):
            user = self.bot.get_user(user_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.HTTPException:
                    continue
            if user is None:
                continue
            try:
                await user.send(message)
            except (discord.Forbidden, discord.HTTPException):
                continue

    async def handle_start(self):
        """處理競標從預備狀態轉為正式開始時的工作。"""
        if self.start_event_handled:
            return
        self.start_event_handled = True
        if self.view:
            await self.view.transition_to_bidding()
        await self.notify_reminders()

    @staticmethod
    def _safe_filename(name: str) -> str:
        # Windows 禁止: \ / : * ? " < > |   ── 全平台最大公約數
        return re.sub(r'[\\/*?:"<>|]', '', name).replace(' ', '_')

class BidButton(discord.ui.Button):
    """出價按鈕元件。"""

    def __init__(self, auction: Auction):
        emoji = discord.PartialEmoji(id=common.cake_emoji_id, name="cake")
        super().__init__(label=f"出價!({auction.next_price()})", style=discord.ButtonStyle.green, emoji=emoji)
        self.auction = auction

    async def callback(self, interaction: discord.Interaction):
        """處理出價按鈕點擊。"""
        async with self.auction.lock:
            try:
                await self.auction.place_bid(interaction)
            except ValueError as e:
                # 使用 embed 呈現錯誤訊息，並僅對使用者可見
                error_embed = Embed(title="❌ 出價失敗", description=str(e), color=common.bot_error_color)
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
                return
        # ---------------- 出價成功 ----------------
        # 更新按鈕文字
        self.label = f"出價!({self.auction.next_price()})"
        success_embed = Embed(title="✅ 出價成功", description=f"你成功以 **{self.auction.highest_bid}** 塊{common.cake_emoji}出價!", color=common.bot_color)
        await interaction.response.send_message(embed=success_embed, ephemeral=True)
        # 4 秒後自動刪除出價成功訊息
        async def delete_after_delay():
            try:
                await asyncio.sleep(4)
                msg = await interaction.original_response()
                await msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass  # 訊息可能已被user刪除
        asyncio.create_task(delete_after_delay())
        await AuctionView.update_embed(self.auction)
        await self.auction.write_log(interaction.user.display_name)

class ReminderButton(discord.ui.Button):
    """競標尚未開始時提供提醒的按鈕。"""

    def __init__(self, auction: Auction):
        super().__init__(label="開始後提醒我!", style=discord.ButtonStyle.blurple)
        self.auction = auction

    async def callback(self, interaction: discord.Interaction):
        """收集希望在競標開始時收到通知的使用者。"""
        if self.auction.started:
            await interaction.response.send_message("競標已經開始囉，快去出價吧!", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id in self.auction.reminder_users:
            await interaction.response.send_message("提醒已設定，開始時會傳送私訊通知你。", ephemeral=True)
            return

        self.auction.reminder_users.add(user_id)
        await interaction.response.send_message("提醒設置成功! 競標開始時會以私訊提醒你。", ephemeral=True)

class AuctionView(discord.ui.View):
    """提供按鈕並定期更新 embed 的 View。"""

    def __init__(self, auction: Auction):
        super().__init__(timeout=None)
        self.auction = auction
        self.bid_button: BidButton | None = None
        self.reminder_button: ReminderButton | None = None
        if auction.started:
            self.bid_button = BidButton(auction)
            self.add_item(self.bid_button)
        else:
            self.reminder_button = ReminderButton(auction)
            self.add_item(self.reminder_button)
        auction.view = self
        # 將競標交給背景迴圈持續追蹤
        AuctionLoop.instance().track(auction)

    async def on_timeout(self):
        # 由 AuctionLoop 統一處理結束，不在此處理
        pass

    async def transition_to_bidding(self):
        """競標開始後，把提醒按鈕換成出價按鈕。"""
        if self.bid_button is not None:
            return
        self.clear_items()
        self.reminder_button = None
        self.bid_button = BidButton(self.auction)
        self.add_item(self.bid_button)
        await AuctionView.update_embed(self.auction)

    @staticmethod
    async def update_embed(auction: Auction):
        embed = generate_embed(auction)
        await auction.message.edit(embed=embed, view=auction.view)

class AuctionLoop:
    """背景持續更新所有進行中競標的單例。"""

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.active: dict[int, Auction] = {}  # message_id -> Auction
        self.last_update: dict[int, float] = {}
        self.task = asyncio.create_task(self._run())

    def track(self, auction: Auction):
        """加入追蹤。"""
        self.active[auction.message.id] = auction
        self.last_update[auction.message.id] = 0.0

    async def _run(self):
        while True:
            await asyncio.sleep(1)  # 固定輪詢間隔
            now = asyncio.get_event_loop().time()
            finished: list[int] = []
            for msg_id, auction in list(self.active.items()):
                if not auction.start_event_handled and auction.started:
                    await auction.handle_start()
                    self.last_update[msg_id] = now

                if not auction.started:
                    interval = 10
                    last = self.last_update.get(msg_id, 0.0)
                    if now - last >= interval:
                        await AuctionView.update_embed(auction)
                        self.last_update[msg_id] = now
                    continue

                remaining = auction.remaining()
                if remaining <= 0:
                    finished.append(msg_id)
                    await self._settle(auction)  # 結算
                else:
                    should_update = False
                    if remaining > 60:
                        # 剩餘時間 > 60 秒時，每 60 秒更新一次
                        interval = 60
                        last = self.last_update.get(msg_id, 0.0)
                        if now - last >= interval:
                            should_update = True
                    else:
                        # 剩餘時間 <= 60 秒時，在特定時間點更新（30、15、5 秒）
                        if remaining == 30 or remaining == 15 or remaining == 5:
                            should_update = True
                    if should_update:
                        await AuctionView.update_embed(auction)
                        self.last_update[msg_id] = now
            for msg_id in finished:
                del self.active[msg_id]
                self.last_update.pop(msg_id, None)

    async def _settle(self, auction: Auction):
        # 1. 禁用按鈕並顯示 00:00
        if auction.view:
            for child in auction.view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            await auction.message.edit(embed=generate_embed(auction), view=auction.view)  # embed 亦更新為 00:00

        # 2. 退款未得標者
        for uid, reserved in auction.bid_history.items():
            if uid != auction.highest_bidder:
                await auction.refund(uid, reserved)

        # 3. 撥款給賣家
        if auction.highest_bidder is not None:
            userdata_collection = common.mongo_storage.get_collection("userdata")
            defaults = common.mongo_storage.get_user_defaults()
            await userdata_collection.update_one(
                {"_id": str(auction.author_id)},
                {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": auction.highest_bid}},
                upsert=True,
            )

        # 4. 公告結果
        if auction.highest_bidder is None:
            await auction.message.channel.send(f"競標結束! **{auction.item}** 流標了!")
        else:
            winner = f"<@{auction.highest_bidder}>"
            await auction.message.channel.send(
                f"競標結束! 恭喜 {winner} 以 **{auction.highest_bid}** 塊{common.cake_emoji}得標 **{auction.item}** !"
            )

# ------------------------------------------------------------
#  產生 embed 區塊
# ------------------------------------------------------------

def generate_embed(auction: Auction) -> Embed:
    def format_span(seconds: int) -> str:
        seconds = max(0, seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    tz_taipei = timezone(timedelta(hours=8))
    end_local = auction.end_time.astimezone(tz_taipei)
    end_str = end_local.strftime("%Y-%m-%d %H:%M:%S")

    if not auction.started:
        start_remaining = auction.time_until_start()
        start_local = auction.start_time.astimezone(tz_taipei)
        start_str = start_local.strftime("%Y-%m-%d %H:%M:%S")
        duration_seconds = int((auction.end_time - auction.start_time).total_seconds())
        description = (
            f"競標開始剩餘時間: **{format_span(start_remaining)}**\n"
            f"預計開始時間: {start_str} (UTC+8)\n"
            f"競標時長: {format_span(duration_seconds)}"
        )
    else:
        remaining = auction.remaining()
        description = (
            f"剩餘時間: **{format_span(remaining)}**\n"
            f"結束時間: {end_str} (UTC+8)"
        )

    embed = Embed(title="🎉 競標中 – " + auction.item,
                  description=description,
                  color=common.bot_color)

    # 起標價與增額出價
    embed.add_field(name="起標價", value=str(auction.start_price), inline=True)
    embed.add_field(name="增額出價", value=str(auction.increment), inline=True)

    # 最高價與出價次數
    if auction.highest_bidder:
        embed.add_field(name="目前最高價", value=f"{auction.highest_bid} <@{auction.highest_bidder}>", inline=False)
    else:
        embed.add_field(name="目前最高價", value="尚無", inline=False)
    embed.add_field(name="此商品出價次數", value=str(auction.bid_count), inline=False)

    embed.set_footer(text="⚠️ 若剩餘時間低於 60 秒後有人出價，系統將自動延長 30 秒。")
    return embed

class Trade(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        
    # =====================================================
    #  建立競標指令
    # =====================================================

    class ChannelSelectView(discord.ui.View):
        """頻道選擇 View，用於選擇競標發布頻道。"""
        
        def __init__(self, parent_cog: "Trade"):
            super().__init__(timeout=300)  # 5分鐘超時
            self.parent_cog = parent_cog
            self.selected_channel: discord.TextChannel | None = None

        @discord.ui.select(
            cls=discord.ui.ChannelSelect,
            placeholder="選擇要發布競標的頻道",
            channel_types=[discord.ChannelType.text]
        )
        async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
            """處理頻道選擇。"""
            self.selected_channel = select.values[0]
            # 顯示 Modal
            modal = self.parent_cog.CreateBidModal(self.parent_cog, self.selected_channel.id)
            await interaction.response.send_modal(modal)

        async def on_timeout(self):
            """View 超時時清理。"""
            self.stop()

    class CreateBidModal(discord.ui.Modal, title="建立競標"):
        item = discord.ui.TextInput(label="商品", placeholder="300元禮物卡", required=True)
        start_price = discord.ui.TextInput(label="起標價", placeholder="輸入數字", required=True)
        increment = discord.ui.TextInput(label="增額出價", placeholder="每次最少加多少", required=True)
        duration = discord.ui.TextInput(label="持續時間 (分鐘)", placeholder="例如 10", required=True)
        preparation = discord.ui.TextInput(label="準備時間 (分鐘)", placeholder="例如 5 (可留白)", required=False)

        def __init__(self, parent_cog: "Trade", channel_id: int):
            super().__init__()
            self.parent_cog = parent_cog
            self.channel_id = channel_id

        async def on_submit(self, interaction: discord.Interaction):
            # 參數驗證
            try:
                start = int(self.start_price.value)
                inc = int(self.increment.value)
                dur_minutes = int(self.duration.value)
                prep_value = self.preparation.value.strip()
                prep_minutes = int(prep_value) if prep_value else 0
                if start <= 0 or inc <= 0 or dur_minutes <= 0 or prep_minutes < 0:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message("輸入格式錯誤，請確認皆為正整數。", ephemeral=True)
                return

            now = datetime.now(timezone.utc)
            start_time = now + timedelta(minutes=prep_minutes)
            end_time = start_time + timedelta(minutes=dur_minutes)
            channel = interaction.guild.get_channel(self.channel_id)
            if channel is None:
                await interaction.response.send_message("找不到指定的頻道，請重新選擇。", ephemeral=True)
                return

            dummy_msg = await channel.send("稍等…正在建立競標…")

            auction = Auction(
                item=self.item.value,
                start_price=start,
                increment=inc,
                end_time=end_time,
                author_id=interaction.user.id,
                message=dummy_msg,
                bot=self.parent_cog.bot,
                start_time=start_time
            )

            embed = generate_embed(auction)
            view = AuctionView(auction)
            await dummy_msg.edit(content="", embed=embed, view=view)
            await interaction.response.send_message("競標已建立!", ephemeral=True)

    @app_commands.command(name="create_bid", description="建立競標交易")
    async def create_bid(self, interaction: discord.Interaction):
        """先選擇頻道，然後跳出 Modal 讓使用者輸入競標資訊。"""
        view = self.ChannelSelectView(self)
        embed = Embed(
            title="建立競標",
            description="請先選擇要發布競標的頻道",
            color=common.bot_color
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


    #Nitro Booster 每月可以兌換一次稱號
    @app_commands.command(name = "redeem_member_role", description = "兌換自訂稱號(每月一次)")
    @app_commands.describe(rolename="你想要兌換的稱號名",colorhex="顏色色碼，6位數HEX格式(EX:FFFFFF = 白色，000000 = 黑色")
    @app_commands.rename(rolename="稱號名",colorhex="色碼")
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
                
            async with common.jsonio_lock:
                now = datetime.now()
                memberid = str(interaction.user.id)
                user_data = await common.mongo_storage.get_user(memberid)
                if user_data is None:
                    await common.mongo_storage.ensure_user_document(memberid)
                    user_data = await common.mongo_storage.get_user(memberid)
                if user_data is None:
                    await interaction.response.send_message(embed=Embed(title="兌換自訂稱號",description="兌換失敗:讀取使用者資料失敗。",color=common.bot_error_color))
                    return
                user_data = {field_name: field_value for field_name, field_value in user_data.items() if field_name != "_id"}
                if "redeem member role interval" in user_data:
                    last_redeem = datetime.strptime(user_data['redeem member role interval'], '%Y-%m-%d %H:%M')
                    #如果有資料，則進行天數比對
                    if now - last_redeem >=timedelta(days=30):
                        user_data['redeem member role interval'] = now.strftime('%Y-%m-%d %H:%M')
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
                    user_data['redeem member role interval'] = now.strftime('%Y-%m-%d %H:%M')
                #添加身分組
                await interaction.guild.create_role(name=rolename,color=colorhex,reason="Nitro Booster兌換每月自訂稱號")
                await interaction.user.add_roles(discord.utils.get(interaction.guild.roles,name=rolename))
                await interaction.response.send_message(embed=Embed(title="兌換自訂稱號",description=f"兌換成功!你現在擁有《 **{rolename}** 》稱號。",color=common.bot_color))
                await common.mongo_storage.upsert_user(memberid, user_data)
            
    @app_commands.command(name = "cake_give", description = "贈送蛋糕")
    @app_commands.describe(member_give="你想要給予的人(使用提及)",amount="給予的蛋糕數量")
    @app_commands.rename(member_give="提及用戶",amount="數量")
    async def cake_give(self,interaction,member_give: discord.Member,amount: int):
        userid = str(interaction.user.id)
        if interaction.user == member_give:
            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:你無法贈送給自己。",color=common.bot_error_color))
            return
        if member_give.bot:
            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:你無法贈送給bot。",color=common.bot_error_color))
            return
        if amount <= 0:
            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:請輸入有效的數字。",color=common.bot_error_color))
            return

        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        spend_result = await userdata_collection.find_one_and_update(
            {"_id": userid, "cake": {"$gte": amount}},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": -amount}},
            upsert=False,
            return_document=common.ReturnDocument.AFTER,
        )
        if spend_result is None:
            user_data = await common.mongo_storage.ensure_user_document(userid)
            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description=f"錯誤:{common.cake_emoji}不足，你只有**{user_data.get('cake', 0)}**塊{common.cake_emoji}。",color=common.bot_error_color))
            return
        try:
            await userdata_collection.update_one(
                {"_id": str(member_give.id)},
                {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": amount}},
                upsert=True,
            )
        except Exception:
            await userdata_collection.update_one({"_id": userid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": amount}}, upsert=True)
            raise

        await interaction.response.send_message(embed=Embed(title="給予蛋糕",description=f"你給予了**{amount}**塊{common.cake_emoji}給<@{str(member_give.id)}>",color=common.bot_color))


async def setup(client:commands.Bot):
    await client.add_cog(Trade(client))
