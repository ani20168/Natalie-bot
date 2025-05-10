import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime,timezone,timedelta
import re
import asyncio

class Auction:
    """單一競標的執行中狀態。"""

    # -----------------------------
    # 防搶標參數 (類別層級)
    # -----------------------------
    EXTEND_THRESHOLD = 60  # 剩餘秒數 ≤ 此值時觸發延長
    EXTEND_DURATION = 30   # 每次延長的秒數

    def __init__(self, *, item: str, start_price: int, increment: int,
                 end_time: datetime, author_id: int, message: discord.Message):
        self.item = item                        # 商品名稱
        self.start_price = start_price          # 起標價
        self.increment = increment              # 每次最小加價
        self.end_time = end_time                # 競標結束時間 (UTC)
        self.author_id = author_id              # 建立者 ID
        self.message = message                  # Discord 訊息物件 (用來更新)
        self.view: "AuctionView | None" = None  # 留存 View 物件以便後續更新

        # 競標狀態
        self.highest_bid = start_price - increment  # 設為 "尚未有人出價" 的前置值
        self.highest_bidder: int | None = None      # 目前最高出價者 ID
        self.bid_count: int = 0                     # 出價次數
        self.bid_history: dict[int, int] = {}       # 用戶預扣金額紀錄 {user_id: 已預扣總額}
        self.lock = asyncio.Lock()                  # 保護競態條件

    # ----------------------------------------------------
    # 工具函式
    # ----------------------------------------------------
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
        data = common.dataload()
        if str(user_id) not in data or data[str(user_id)]["cake"] < amount:
            raise ValueError("蛋糕不足")
        data[str(user_id)]["cake"] -= amount
        common.datawrite(data)

    async def refund(self, user_id: int, amount: int):
        """退款給指定用戶。"""
        async with common.jsonio_lock:
            data = common.dataload()
            if str(user_id) not in data:
                data[str(user_id)] = {"cake": 0}
            data[str(user_id)]["cake"] += amount
            common.datawrite(data)

    async def place_bid(self, interaction: discord.Interaction):
        """處理按鈕互動產生的出價。必須於 self.lock 內呼叫。"""
        bidder_id = interaction.user.id
        # 固定最高價者不得連續出價
        if bidder_id == self.highest_bidder:
            raise ValueError("你已是最高出價者，無法再次出價")

        next_price = self.next_price()
        previously_reserved = self.bid_history.get(bidder_id, 0)
        additional_needed = next_price - previously_reserved
        if additional_needed <= 0:
            raise ValueError("你的出價已經是目前最高價")
        # 預扣差額蛋糕
        async with common.jsonio_lock:
            data = common.dataload()
            if str(bidder_id) not in data or data[str(bidder_id)]["cake"] < additional_needed:
                raise ValueError("蛋糕不足，無法出價")
            data[str(bidder_id)]["cake"] -= additional_needed
            common.datawrite(data)

        # 更新競標狀態
        self.bid_history[bidder_id] = previously_reserved + additional_needed
        self.highest_bid = next_price
        self.highest_bidder = bidder_id
        self.bid_count += 1

        # 防搶標：如剩餘時間過短則延長
        if self.needs_extension():
            self.end_time += timedelta(seconds=self.EXTEND_DURATION)

class BidButton(discord.ui.Button):
    """出價按鈕元件。"""

    def __init__(self, auction: Auction):
        super().__init__(label=f"出價!({auction.next_price()})", style=discord.ButtonStyle.green)
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
        success_embed = Embed(title="✅ 出價成功", description=f"你成功以 **{self.auction.highest_bid}** 出價!", color=common.bot_color)
        await interaction.response.send_message(embed=success_embed, ephemeral=True)
        await AuctionView.update_embed(self.auction)

class AuctionView(discord.ui.View):
    """提供按鈕並定期更新 embed 的 View。"""

    def __init__(self, auction: Auction):
        super().__init__(timeout=None)
        self.auction = auction
        self.bid_button = BidButton(auction)
        self.add_item(self.bid_button)
        auction.view = self
        # 將競標交給背景迴圈持續追蹤
        AuctionLoop.instance().track(auction)

    async def on_timeout(self):
        # 由 AuctionLoop 統一處理結束，不在此處理
        pass

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
        self.task = asyncio.create_task(self._run())

    def track(self, auction: Auction):
        """加入追蹤。"""
        self.active[auction.message.id] = auction

    async def _run(self):
        while True:
            await asyncio.sleep(2)  # 每 2 秒更新
            finished: list[int] = []
            for msg_id, auction in list(self.active.items()):
                remaining = auction.remaining()
                if remaining <= 0:
                    finished.append(msg_id)
                    await self._settle(auction)  # 結算
                else:
                    await AuctionView.update_embed(auction)  # 更新剩餘時間
            for msg_id in finished:
                del self.active[msg_id]

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
            async with common.jsonio_lock:
                data = common.dataload()
                data.setdefault(str(auction.author_id), {"cake": 0})
                data[str(auction.author_id)]["cake"] += auction.highest_bid
                common.datawrite(data)

        # 4. 公告結果
        winner = f"<@{auction.highest_bidder}>" if auction.highest_bidder else "無人"
        await auction.message.channel.send(f"競標結束! 恭喜 {winner} 以 **{auction.highest_bid}** 塊蛋糕得標 **{auction.item}** !")

# ------------------------------------------------------------
#  產生 embed 區塊
# ------------------------------------------------------------

def generate_embed(auction: Auction) -> Embed:
    remaining = max(0, auction.remaining())
    h, rem = divmod(remaining, 3600)
    m, s = divmod(rem, 60)

    # 動態格式：>=1 小時顯示 HH:MM:SS，否則顯示 MM:SS
    if h:
        remain_str = f"{h:02d}:{m:02d}:{s:02d}"
    else:
        remain_str = f"{m:02d}:{s:02d}"

    # 將結束時間轉為 UTC+8 並格式化
    tz_taipei = timezone(timedelta(hours=8))
    end_local = auction.end_time.astimezone(tz_taipei)
    end_str = end_local.strftime("%Y-%m-%d %H:%M:%S")

    description = (
        f"剩餘時間: **{remain_str}**\n"
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
        self.auction_channel_id = 1370620274650648667  #拍賣所 頻道 ID

    # =====================================================
    #  建立競標指令
    # =====================================================

    class CreateBidModal(discord.ui.Modal, title="建立競標"):
        item = discord.ui.TextInput(label="商品", placeholder="300元禮物卡", required=True)
        start_price = discord.ui.TextInput(label="起標價", placeholder="輸入數字", required=True)
        increment = discord.ui.TextInput(label="增額出價", placeholder="每次最少加多少", required=True)
        duration = discord.ui.TextInput(label="持續時間 (分鐘)", placeholder="例如 10", required=True)

        def __init__(self, parent_cog: "Trade"):
            super().__init__()
            self.parent_cog = parent_cog

        async def on_submit(self, interaction: discord.Interaction):
            # 參數驗證
            try:
                start = int(self.start_price.value)
                inc = int(self.increment.value)
                dur_minutes = int(self.duration.value)
                if start <= 0 or inc <= 0 or dur_minutes <= 0:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message("輸入格式錯誤，請確認皆為正整數。", ephemeral=True)
                return

            end_time = datetime.now(timezone.utc) + timedelta(minutes=dur_minutes)
            channel = interaction.guild.get_channel(self.parent_cog.auction_channel_id)
            if channel is None:
                await interaction.response.send_message("找不到拍賣所頻道，請先設定。", ephemeral=True)
                return

            dummy_msg = await channel.send("稍等…正在建立競標…")

            auction = Auction(
                item=self.item.value,
                start_price=start,
                increment=inc,
                end_time=end_time,
                author_id=interaction.user.id,
                message=dummy_msg
            )

            embed = generate_embed(auction)
            view = AuctionView(auction)
            await dummy_msg.edit(content="", embed=embed, view=view)
            await interaction.response.send_message("競標已建立!", ephemeral=True)

    @app_commands.command(name="create_bid", description="建立競標交易")
    async def create_bid(self, interaction: discord.Interaction):
        """跳出 Modal 讓使用者輸入競標資訊。"""
        await interaction.response.send_modal(self.CreateBidModal(self))


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
    @app_commands.describe(member_give="你想要給予的人(使用提及)",amount="給予的蛋糕數量")
    @app_commands.rename(member_give="提及用戶",amount="數量")
    async def cake_give(self,interaction,member_give: discord.Member,amount: int):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            user_data = common.dataload()
            if interaction.user == member_give:
                await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:你無法贈送給自己。",color=common.bot_error_color))
                return
            if member_give.bot:
                await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:你無法贈送給bot。",color=common.bot_error_color))
                return
            if amount <= 0:
                await interaction.response.send_message(embed=Embed(title="給予蛋糕",description="錯誤:請輸入有效的數字。",color=common.bot_error_color))
                return
            if user_data[userid]["cake"] < amount:
                await interaction.response.send_message(embed=Embed(title="給予蛋糕",description=f"錯誤:蛋糕不足，你只有**{user_data[userid]['cake']}**塊蛋糕。",color=common.bot_error_color))
                return

            user_data[userid]["cake"] -= amount
            user_data[str(member_give.id)]["cake"] += amount
            common.datawrite(user_data)

            await interaction.response.send_message(embed=Embed(title="給予蛋糕",description=f"你給予了**{amount}**塊蛋糕給<@{str(member_give.id)}>",color=common.bot_color))


async def setup(client:commands.Bot):
    await client.add_cog(Trade(client))