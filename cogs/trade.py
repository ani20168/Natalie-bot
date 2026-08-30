import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from datetime import datetime,timezone,timedelta
import re
from pathlib import Path
import asyncio
import random
import traceback

class Auction:
    """單一競標的執行中狀態。"""

    def __init__(self, *, auction_id: int, item: str, start_price: int, increment: int,
                 end_time: datetime, author_id: int, bot: commands.Bot,
                 channel_id: int, message_id: int = 0,
                 message: discord.Message | None = None,
                 start_time: datetime | None = None):
        self.extend_threshold = 60
        self.extend_duration = 30
        self.log_dir = Path("log/bid")
        self.auction_id = auction_id
        self.item = item
        self.start_price = start_price
        self.increment = increment
        self.end_time = end_time
        self.author_id = author_id
        self.channel_id = channel_id
        self.message = message
        self.message_id = message.id if message is not None else message_id
        self.view: "AuctionView | None" = None
        self.bot = bot
        self.highest_bid = start_price - increment
        self.highest_bidder: int | None = None
        self.bid_count: int = 0
        self.bid_history: dict[int, int] = {}
        self.lock = asyncio.Lock()
        self.status = "active"
        self.log_path = self.log_dir / f"{self.auction_id}_{self.safe_filename(self.item)}.txt"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.start_time = start_time or datetime.now(timezone.utc)
        self.reminder_users: set[int] = set()
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
        return self.remaining() <= self.extend_threshold

    def to_document(self) -> dict:
        """
        轉成 Mongo 文件。

        Returns:
            document (dict): "{'_id': 1, 'item': '禮物卡', 'status': 'active'}"
        """
        return {
            "_id": self.auction_id,
            "item": self.item,
            "start_price": self.start_price,
            "increment": self.increment,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "author_id": self.author_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "highest_bid": self.highest_bid,
            "highest_bidder": self.highest_bidder,
            "bid_count": self.bid_count,
            "bid_history": {str(user_id): amount for user_id, amount in self.bid_history.items()},
            "reminder_users": list(self.reminder_users),
            "status": self.status,
            "start_event_handled": self.start_event_handled,
            "reminder_notified": self.reminder_notified,
        }

    async def save(self):
        """將目前狀態寫入 Mongo。"""
        collection = common.mongo_storage.get_collection("auction")
        await collection.replace_one({"_id": self.auction_id}, self.to_document(), upsert=True)

    async def refund(self, user_id: int, amount: int):
        """
        退款給指定用戶。

        Args:
            user_id (int): "410847926236086272"
            amount (int): "65000"
        """
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        await userdata_collection.update_one({"_id": str(user_id)}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": amount}}, upsert=True)

    async def place_bid(self, bidder_id: int, expected_price: int):
        """
        處理網頁送出的出價。必須於 self.lock 內呼叫。

        Args:
            bidder_id (int): "410847926236086272"
            expected_price (int): "65000"
        """
        if self.status == "ended" or self.remaining() <= 0:
            raise ValueError("競標已結束")
        if not self.started:
            raise ValueError("競標尚未開始，請稍候再出價")
        if bidder_id == self.highest_bidder:
            raise ValueError("你已是最高出價者，無法再次出價")

        next_price = self.next_price()
        if expected_price != next_price:
            raise ValueError("此價格已經有人出價")
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

        self.bid_history[bidder_id] = previously_reserved + additional_needed
        self.highest_bid = next_price
        self.highest_bidder = bidder_id
        self.bid_count += 1
        if self.needs_extension():
            self.end_time += timedelta(seconds=self.extend_duration)
        await self.save()

    def append_log_line(self, line: str):
        """
        將一行文字附加到競標日誌。

        Args:
            line (str): "第1次出價:ani 出價65000個蛋糕\\n"
        """
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(line)

    async def write_log(self, bidder_name: str):
        """
        將成功出價寫入 log/bid/<ID_商品>.txt

        Args:
            bidder_name (str): "ani"
        """
        line = f"第{self.bid_count}次出價:{bidder_name} 出價{self.highest_bid}個蛋糕\n"
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.append_log_line, line)

    async def notify_reminders(self):
        """通知設定提醒的用戶競標已經開始。"""
        if not self.reminder_users or self.reminder_notified:
            return
        self.reminder_notified = True
        lines = [f"競標 **{self.item}** 已經開始囉！"]
        if self.message is not None:
            lines.append(f"直接前往：{self.message.jump_url}")
        house = getattr(self.bot, "auction_house", None)
        if house is not None:
            lines.append(f"拍賣所：{house.page_url()}")
        message = "\n".join(lines)
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
        await self.save()

    @classmethod
    def from_document(cls, document: dict, message: discord.Message | None, bot: commands.Bot) -> "Auction":
        """
        從 Mongo 文件還原競標。

        Args:
            document (dict): "{'_id': 1, 'item': '禮物卡'}"
            message (discord.Message | None): Discord 訊息
            bot (commands.Bot): Bot 實例

        Returns:
            auction (Auction): 還原後的競標
        """
        auction = cls(
            auction_id=int(document["_id"]),
            item=document["item"],
            start_price=int(document["start_price"]),
            increment=int(document["increment"]),
            end_time=datetime.fromisoformat(document["end_time"]),
            author_id=int(document["author_id"]),
            bot=bot,
            channel_id=int(document["channel_id"]),
            message_id=int(document.get("message_id", 0)),
            message=message,
            start_time=datetime.fromisoformat(document["start_time"]),
        )
        auction.highest_bid = int(document.get("highest_bid", auction.start_price - auction.increment))
        highest_bidder = document.get("highest_bidder")
        auction.highest_bidder = int(highest_bidder) if highest_bidder is not None else None
        auction.bid_count = int(document.get("bid_count", 0))
        auction.bid_history = {int(user_id): int(amount) for user_id, amount in document.get("bid_history", {}).items()}
        auction.reminder_users = {int(user_id) for user_id in document.get("reminder_users", [])}
        auction.start_event_handled = bool(document.get("start_event_handled", False))
        auction.reminder_notified = bool(document.get("reminder_notified", False))
        auction.status = str(document.get("status", "active"))
        return auction

    @staticmethod
    def safe_filename(name: str) -> str:
        """
        去掉檔名不合法字元。

        Args:
            name (str): "300元禮物卡"

        Returns:
            safe_name (str): "300元禮物卡"
        """
        return re.sub(r'[\\/*?:"<>|]', '', name).replace(' ', '_')

class GoToAuctionButton(discord.ui.Button):
    """導向網頁拍賣所的連結按鈕。"""

    def __init__(self, page_url: str):
        super().__init__(label="前往競標", style=discord.ButtonStyle.link, url=page_url)

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
        await self.auction.save()
        await interaction.response.send_message("提醒設置成功! 競標開始時會以私訊提醒你。", ephemeral=True)

class AuctionView(discord.ui.View):
    """Discord embed 上的前往競標連結，以及開始前記得按鈕。"""

    def __init__(self, auction: Auction, page_url: str):
        super().__init__(timeout=None)
        self.auction = auction
        self.page_url = page_url
        self.reminder_button: ReminderButton | None = None
        self.add_item(GoToAuctionButton(page_url))
        if not auction.started:
            self.reminder_button = ReminderButton(auction)
            self.add_item(self.reminder_button)
        auction.view = self

    async def on_timeout(self):
        pass

    async def transition_to_bidding(self):
        """競標開始後移除提醒按鈕，只留前往競標。"""
        if self.reminder_button is None:
            return
        self.remove_item(self.reminder_button)
        self.reminder_button = None
        await AuctionView.update_embed(self.auction)

    @staticmethod
    async def update_embed(auction: Auction):
        """
        更新 Discord 競標 embed。

        Args:
            auction (Auction): 要更新的競標
        """
        if auction.message is None:
            return
        embed = generate_embed(auction)
        await auction.message.edit(embed=embed, view=auction.view)

class BidRequest:
    """網頁出價佇列中的一筆請求。"""

    def __init__(self, auction_id: int, user_id: int, expected_price: int, display_name: str, result_future: asyncio.Future):
        self.auction_id = auction_id
        self.user_id = user_id
        self.expected_price = expected_price
        self.display_name = display_name
        self.result_future = result_future

class AuctionHouse:
    """管理進行中競標、embed 更新與出價佇列。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_update_seconds_before_start = 30
        self.embed_update_seconds_after_start = 30
        self.embed_update_seconds_last_minute = 15
        self.last_minute_threshold = 60
        self.ended_list_limit = 100
        self.active: dict[int, Auction] = {}
        self.last_update: dict[int, float] = {}
        self.bid_queue: asyncio.Queue[BidRequest] = asyncio.Queue()
        self.loop_task: asyncio.Task | None = None
        self.queue_task: asyncio.Task | None = None

    def start_tasks(self):
        """啟動 embed 更新與出價佇列背景工作。"""
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = asyncio.create_task(self.run_embed_loop())
        if self.queue_task is None or self.queue_task.done():
            self.queue_task = asyncio.create_task(self.run_bid_queue())

    def stop_tasks(self):
        """停止背景工作。"""
        if self.loop_task is not None:
            self.loop_task.cancel()
            self.loop_task = None
        if self.queue_task is not None:
            self.queue_task.cancel()
            self.queue_task = None

    def page_url(self) -> str:
        """
        組出網頁拍賣所網址。

        Returns:
            url (str): "https://fake-sister.ani20168.com/auction"
        """
        panel = getattr(self.bot, "web_panel", None)
        if panel is not None and panel.public_base_url:
            return f"{panel.public_base_url}/auction"
        port = getattr(panel, "port", 8080) if panel is not None else 8080
        return f"http://localhost:{port}/auction"

    def track(self, auction: Auction):
        """
        加入進行中追蹤。

        Args:
            auction (Auction): 要追蹤的競標
        """
        self.active[auction.auction_id] = auction
        self.last_update[auction.auction_id] = asyncio.get_event_loop().time()

    def get_active(self, auction_id: int) -> Auction | None:
        """
        取得進行中的競標。

        Args:
            auction_id (int): "1"

        Returns:
            auction (Auction | None): 進行中的競標
        """
        return self.active.get(auction_id)

    async def allocate_id(self) -> int:
        """
        配置下一個競標 ID（從 1 開始）。

        Returns:
            auction_id (int): "1"
        """
        collection = common.mongo_storage.get_collection("auction")
        result = await collection.find_one_and_update(
            {"_id": "counter"},
            {"$inc": {"next_id": 1}},
            upsert=True,
            return_document=common.ReturnDocument.AFTER,
        )
        return int(result["next_id"])

    async def register(self, auction: Auction):
        """
        寫入資料庫並開始追蹤。

        Args:
            auction (Auction): 新建立的競標
        """
        await auction.save()
        self.track(auction)

    async def enqueue_bid(self, auction_id: int, user_id: int, expected_price: int, display_name: str) -> dict:
        """
        將出價放入佇列，依序處理後回傳結果。

        Args:
            auction_id (int): "1"
            user_id (int): "410847926236086272"
            expected_price (int): "65000"
            display_name (str): "ani"

        Returns:
            result (dict): "{'ok': True, 'price': 65000}"
        """
        result_future = asyncio.get_running_loop().create_future()
        await self.bid_queue.put(BidRequest(auction_id, user_id, expected_price, display_name, result_future))
        return await result_future

    async def run_bid_queue(self):
        """依序處理網頁出價，避免兩人同時點同一價格。"""
        while True:
            request = await self.bid_queue.get()
            try:
                result = await self.process_bid(request)
            except Exception:
                traceback.print_exc()
                result = {"ok": False, "error": "系統錯誤，請稍後再試"}
            if not request.result_future.done():
                request.result_future.set_result(result)

    async def process_bid(self, request: BidRequest) -> dict:
        """
        處理單筆出價。

        Args:
            request (BidRequest): 佇列中的出價

        Returns:
            result (dict): "{'ok': True, 'price': 65000}"
        """
        auction = self.get_active(request.auction_id)
        if auction is None:
            return {"ok": False, "error": "競標不存在或已結束"}
        async with auction.lock:
            try:
                await auction.place_bid(request.user_id, request.expected_price)
            except ValueError as error:
                return {"ok": False, "error": str(error)}
        await auction.write_log(request.display_name)
        return {"ok": True, "price": auction.highest_bid, "next_price": auction.next_price()}

    async def run_embed_loop(self):
        """依冷卻時間更新 Discord embed，並在到期時結算。"""
        while True:
            await asyncio.sleep(1)
            now = asyncio.get_event_loop().time()
            finished: list[int] = []
            for auction_id, auction in list(self.active.items()):
                try:
                    if not auction.start_event_handled and auction.started:
                        await auction.handle_start()
                        await auction.save()
                        self.last_update[auction_id] = now

                    remaining = auction.remaining()
                    if auction.started and remaining <= 0:
                        await self.settle(auction)
                        if auction.status == "ended":
                            finished.append(auction_id)
                        continue

                    interval = self.embed_interval(auction)
                    last = self.last_update.get(auction_id, 0.0)
                    if now - last >= interval:
                        await AuctionView.update_embed(auction)
                        self.last_update[auction_id] = now
                except Exception:
                    traceback.print_exc()
            for auction_id in finished:
                self.active.pop(auction_id, None)
                self.last_update.pop(auction_id, None)

    def embed_interval(self, auction: Auction) -> int:
        """
        依競標階段決定 Discord embed 更新間隔。

        Args:
            auction (Auction): 進行中的競標

        Returns:
            seconds (int): "30"
        """
        if not auction.started:
            return self.embed_update_seconds_before_start
        if auction.remaining() > self.last_minute_threshold:
            return self.embed_update_seconds_after_start
        return self.embed_update_seconds_last_minute

    async def settle(self, auction: Auction):
        """
        結算競標：退款未得標者、撥款給賣家、在 Discord 公告結果。

        Args:
            auction (Auction): 到期的競標
        """
        async with auction.lock:
            if auction.status == "ended":
                return
            if auction.remaining() > 0:
                return
            auction.status = "ended"
            for user_id, reserved in auction.bid_history.items():
                if user_id != auction.highest_bidder:
                    await auction.refund(user_id, reserved)
            if auction.highest_bidder is not None:
                userdata_collection = common.mongo_storage.get_collection("userdata")
                defaults = common.mongo_storage.get_user_defaults()
                await userdata_collection.update_one(
                    {"_id": str(auction.author_id)},
                    {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": auction.highest_bid}},
                    upsert=True,
                )
            await auction.save()

        if auction.view:
            for child in auction.view.children:
                if isinstance(child, discord.ui.Button) and child.style != discord.ButtonStyle.link:
                    child.disabled = True
        try:
            await AuctionView.update_embed(auction)
        except (discord.HTTPException, discord.NotFound):
            pass

        channel = auction.message.channel if auction.message is not None else self.bot.get_channel(auction.channel_id)
        if channel is None:
            return
        try:
            if auction.highest_bidder is None:
                await channel.send(f"競標結束! **{auction.item}** 流標了!")
            else:
                await channel.send(
                    f"競標結束! 恭喜 <@{auction.highest_bidder}> 以 **{auction.highest_bid}** 塊{common.cake_emoji}得標 **{auction.item}** !"
                )
        except discord.HTTPException:
            pass

    async def restore_active(self):
        """機器人重啟後還原尚未結束的競標。"""
        collection = common.mongo_storage.get_collection("auction")
        async for document in collection.find({"status": "active"}):
            try:
                channel = self.bot.get_channel(int(document["channel_id"]))
                message = None
                if channel is not None:
                    try:
                        message = await channel.fetch_message(int(document["message_id"]))
                    except (discord.NotFound, discord.HTTPException):
                        message = None
                auction = Auction.from_document(document, message, self.bot)
                if message is not None:
                    auction.view = AuctionView(auction, self.page_url())
                    try:
                        await message.edit(embed=generate_embed(auction), view=auction.view)
                    except discord.HTTPException:
                        pass
                self.track(auction)
            except Exception:
                traceback.print_exc()

    def resolve_name(self, user_id: int | None) -> str:
        """
        解析顯示名稱。

        Args:
            user_id (int | None): "410847926236086272"

        Returns:
            name (str): "ani"
        """
        if user_id is None:
            return ""
        guild = self.bot.get_guild(common.fake_sister_server_id)
        member = guild.get_member(user_id) if guild is not None else None
        if member is not None:
            return member.display_name
        user = self.bot.get_user(user_id)
        if user is not None:
            return user.display_name
        return str(user_id)

    def auction_to_public(self, auction: Auction, viewer_id: int | None) -> dict:
        """
        轉成網頁列表用的進行中資料。

        Args:
            auction (Auction): 進行中的競標
            viewer_id (int | None): "410847926236086272"

        Returns:
            payload (dict): "{'id': 1, 'item': '禮物卡'}"
        """
        has_bidder = auction.highest_bidder is not None
        return {
            "id": auction.auction_id,
            "item": auction.item,
            "start_price": auction.start_price,
            "increment": auction.increment,
            "author_name": self.resolve_name(auction.author_id),
            "highest_bid": auction.highest_bid if has_bidder else None,
            "highest_bidder_name": self.resolve_name(auction.highest_bidder) if has_bidder else None,
            "bid_count": auction.bid_count,
            "next_price": auction.next_price(),
            "started": auction.started,
            "start_time": auction.start_time.isoformat(),
            "end_time": auction.end_time.isoformat(),
            "remaining": auction.remaining(),
            "time_until_start": auction.time_until_start(),
            "is_highest_bidder": viewer_id is not None and auction.highest_bidder == viewer_id,
        }

    def ended_document_to_public(self, document: dict) -> dict:
        """
        轉成網頁列表用的已結束資料。

        Args:
            document (dict): "{'_id': 1, 'item': '禮物卡', 'status': 'ended'}"

        Returns:
            payload (dict): "{'id': 1, 'item': '禮物卡'}"
        """
        highest_bidder = document.get("highest_bidder")
        has_bidder = highest_bidder is not None
        return {
            "id": int(document["_id"]),
            "item": document["item"],
            "start_price": int(document.get("start_price", 0)),
            "increment": int(document.get("increment", 0)),
            "author_name": self.resolve_name(int(document["author_id"])) if document.get("author_id") is not None else "",
            "highest_bid": int(document["highest_bid"]) if has_bidder else None,
            "highest_bidder_name": self.resolve_name(int(highest_bidder)) if has_bidder else None,
            "bid_count": int(document.get("bid_count", 0)),
            "ended": True,
        }

    def list_active_public(self, viewer_id: int | None) -> list[dict]:
        """
        進行中競標列表（依 ID 由小到大）。

        Args:
            viewer_id (int | None): "410847926236086272"

        Returns:
            items (list): "[{'id': 1}]"
        """
        auctions = sorted(self.active.values(), key=lambda auction: auction.auction_id)
        return [self.auction_to_public(auction, viewer_id) for auction in auctions]

    async def list_ended_public(self) -> list[dict]:
        """
        已結束競標列表（依 ID 由大到小）。

        Returns:
            items (list): "[{'id': 2}]"
        """
        collection = common.mongo_storage.get_collection("auction")
        items = []
        async for document in collection.find({"status": "ended"}).sort("_id", -1).limit(self.ended_list_limit):
            items.append(self.ended_document_to_public(document))
        return items

# ------------------------------------------------------------
#  產生 embed 區塊
# ------------------------------------------------------------

def format_span(seconds: int) -> str:
    """
    將秒數格式化成倒數文字。

    Args:
        seconds (int): "75"

    Returns:
        text (str): "01:15"
    """
    seconds = max(0, seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def generate_embed(auction: Auction) -> Embed:
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
    embed.add_field(name="發起人", value=f"<@{auction.author_id}>", inline=True)

    # 最高價與出價次數
    if auction.highest_bidder:
        embed.add_field(name="目前最高價", value=f"{auction.highest_bid} <@{auction.highest_bidder}>", inline=False)
    else:
        embed.add_field(name="目前最高價", value="尚無", inline=False)
    embed.add_field(name="此商品出價次數", value=str(auction.bid_count), inline=False)

    embed.set_footer(text=f"⚠️ 若剩餘時間低於 60 秒後有人出價，系統將自動延長 30 秒。 ID:{auction.auction_id}")
    return embed

class Trade(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.cake_give_commission_max_percent = 50
        self.cake_give_commission_min_percent = 1
        self.cake_give_commission_min_level = 1
        self.cake_give_commission_max_level = 300
        self.robbery_target_min_cake = 100000
        self.robbery_self_max_cake = 50000
        self.robbery_cooldown = timedelta(hours=1)
        self.robbery_base_success_rate = 50.0
        self.robbery_success_rate_per_level = 0.5
        self.robbery_cake_per_level = 100
        self.robbery_interval_key = "robbery interval"
        self.auction_house = AuctionHouse(client)
        self.restore_task: asyncio.Task | None = None
        client.auction_house = self.auction_house

    async def cog_load(self):
        """啟動拍賣所背景工作，並在 bot ready 後還原進行中的競標。"""
        self.auction_house.start_tasks()
        self.restore_task = asyncio.create_task(self.restore_auctions_when_ready())

    async def cog_unload(self):
        """停止拍賣所背景工作。"""
        self.auction_house.stop_tasks()
        if self.restore_task is not None:
            self.restore_task.cancel()
            self.restore_task = None

    async def restore_auctions_when_ready(self):
        """等 bot ready 後還原尚未結束的競標。"""
        await self.bot.wait_until_ready()
        await self.auction_house.restore_active()

    def cake_give_commission_percent(self, level: int) -> float:
        """
        依贈送者等級計算 cake_give 抽成百分比（等級越低抽成越高）

        Args:
            level (int): "1"

        Returns:
            percent (float): "50.0"
        """
        if level <= self.cake_give_commission_min_level:
            return float(self.cake_give_commission_max_percent)
        if level >= self.cake_give_commission_max_level:
            return float(self.cake_give_commission_min_percent)
        level_span = self.cake_give_commission_max_level - self.cake_give_commission_min_level
        percent_span = self.cake_give_commission_max_percent - self.cake_give_commission_min_percent
        return self.cake_give_commission_max_percent - percent_span * (level - self.cake_give_commission_min_level) / level_span

    def cake_give_commission_amount(self, amount: int, level: int) -> tuple[int, float]:
        """
        計算 cake_give 抽成數量（無條件捨去）與抽成百分比

        Args:
            amount (int): "100"
            level (int): "1"

        Returns:
            result (tuple): "(50, 50.0)"
        """
        percent = self.cake_give_commission_percent(level)
        commission = int(amount * percent / 100)
        return commission, percent

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

            auction_id = await self.parent_cog.auction_house.allocate_id()
            dummy_msg = await channel.send("稍等…正在建立競標…")

            auction = Auction(
                auction_id=auction_id,
                item=self.item.value,
                start_price=start,
                increment=inc,
                end_time=end_time,
                author_id=interaction.user.id,
                bot=self.parent_cog.bot,
                channel_id=channel.id,
                message=dummy_msg,
                start_time=start_time,
            )

            embed = generate_embed(auction)
            view = AuctionView(auction, self.parent_cog.auction_house.page_url())
            await dummy_msg.edit(content="", embed=embed, view=view)
            await self.parent_cog.auction_house.register(auction)
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
        if any(role.id in (common.nitro_booster_role_id, 419185995078959104) for role in interaction.user.roles):
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
            memberid = str(interaction.user.id)
            interval_key = "redeem member role interval"
            user_data = await common.mongo_storage.get_user(memberid)
            if user_data is None:
                await common.mongo_storage.ensure_user_document(memberid)
                user_data = await common.mongo_storage.get_user(memberid)
            if user_data is None:
                await interaction.response.send_message(embed=Embed(title="兌換自訂稱號",description="兌換失敗:讀取使用者資料失敗。",color=common.bot_error_color))
                return
            if interval_key in user_data:
                last_redeem = datetime.strptime(user_data[interval_key], "%Y-%m-%d %H:%M")
                if now - last_redeem < timedelta(days=30):
                    remaining_time = last_redeem + timedelta(days=30) - now
                    remaining_days, remaining_seconds = divmod(remaining_time.days * 24 * 60 * 60 + remaining_time.seconds, 86400)
                    remaining_hours, remaining_seconds = divmod(remaining_seconds, 3600)
                    await interaction.response.send_message(embed=Embed(
                            title="兌換自訂稱號",
                            description=f"兌換失敗:你每個月只能兌換一次，距離下次兌換還有**{remaining_days}**天**{remaining_hours}**小時。",
                            color=common.bot_error_color))
                    return
            await interaction.guild.create_role(name=rolename,color=colorhex,reason="Nitro Booster兌換每月自訂稱號")
            await interaction.user.add_roles(discord.utils.get(interaction.guild.roles,name=rolename))
            await interaction.response.send_message(embed=Embed(title="兌換自訂稱號",description=f"兌換成功!你現在擁有《 **{rolename}** 》稱號。",color=common.bot_color))
            await common.mongo_storage.update_user_fields(memberid, {interval_key: now.strftime("%Y-%m-%d %H:%M")})
            
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
        #至寶身分組不抽成
        has_super_vip = any(role.id == common.super_vip_id for role in interaction.user.roles)
        if has_super_vip:
            commission, commission_percent = 0, 0.0
        else:
            commission, commission_percent = self.cake_give_commission_amount(amount, spend_result.get("level", 1))
        give_amount = amount - commission
        try:
            await userdata_collection.update_one(
                {"_id": str(member_give.id)},
                {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": give_amount}},
                upsert=True,
            )
            if commission > 0:
                await userdata_collection.update_one(
                    {"_id": str(common.bot_id)},
                    {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": commission}},
                    upsert=True,
                )
        except Exception:
            await userdata_collection.update_one({"_id": userid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": amount}}, upsert=True)
            raise

        message = Embed(title="給予蛋糕",description=f"你給予了**{amount}**塊{common.cake_emoji}給<@{str(member_give.id)}>",color=common.bot_color)
        if commission > 0:
            percent_text = f"{commission_percent:.1f}".rstrip("0").rstrip(".")
            message.add_field(
                name="Natalie偷吃了一些蛋糕",
                value=f"總共有 **{commission}({percent_text}%)** 塊{common.cake_emoji}被偷吃了，剩下 **{give_amount}** 塊{common.cake_emoji}",
                inline=False,
            )
            message.set_footer(text="提示:贈予者等級越低，Natalie更貪吃!")
        await interaction.response.send_message(embed=message)

    def robbery_success_rate(self, robber_level: int, victim_level: int) -> float:
        """
        依雙方等級等差計算搶劫成功率（基礎 50%，每等差 ±0.5%）

        Args:
            robber_level (int): "50"
            victim_level (int): "40"

        Returns:
            rate (float): "55.0"
        """
        rate = self.robbery_base_success_rate + (robber_level - victim_level) * self.robbery_success_rate_per_level
        return max(0.0, min(100.0, rate))

    @app_commands.command(name="robbery", description="搶劫他人的蛋糕")
    @app_commands.describe(member="你想要搶劫的對象")
    @app_commands.rename(member="提及用戶")
    async def robbery(self, interaction: discord.Interaction, member: discord.Member):
        """
        搶劫指定成員的蛋糕；通過條件後進入判定並進入 1 小時冷卻。

        Args:
            interaction (discord.Interaction): "指令互動"
            member (discord.Member): "要搶劫的對象"
        """
        userid = str(interaction.user.id)
        title = "搶劫"
        if interaction.user.id == member.id:
            await interaction.response.send_message(embed=Embed(title=title, description="自己的口袋自己掏不算搶劫啦！", color=common.bot_error_color))
            return
        if member.bot:
            await interaction.response.send_message(embed=Embed(title=title, description="機器人的蛋糕是保養費，動不得！", color=common.bot_error_color))
            return
        if any(role.id == common.super_vip_id for role in member.roles):
            await interaction.response.send_message(embed=Embed(
                title=title,
                description=random.choice([
                    "至寶身上有無敵光環，蛋糕被保護得好好的～",
                    "碰！至寶的蛋糕護盾把你彈開了",
                    "至寶太尊貴了，小偷們都自動繞道",
                ]),
                color=common.bot_error_color,
            ))
            return

        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        robber_data = await common.mongo_storage.ensure_user_document(userid)
        victim_data = await common.mongo_storage.ensure_user_document(str(member.id))
        robber_cake = int(robber_data.get("cake", 0))
        victim_cake = int(victim_data.get("cake", 0))

        if robber_cake > self.robbery_self_max_cake:
            await interaction.response.send_message(embed=Embed(
                title=title,
                description=f"你已經很有錢了！身上超過 **{self.robbery_self_max_cake}** 塊{common.cake_emoji}就不能當小偷喔（目前 **{robber_cake}**）",
                color=common.bot_error_color,
            ))
            return
        if victim_cake < self.robbery_target_min_cake:
            await interaction.response.send_message(embed=Embed(
                title=title,
                description=f"對方窮到只剩 **{victim_cake}** 塊{common.cake_emoji}，放過人家吧（至少要 **{self.robbery_target_min_cake}**）",
                color=common.bot_error_color,
            ))
            return

        now = datetime.now()
        last_robbery_raw = robber_data.get(self.robbery_interval_key)
        if last_robbery_raw:
            try:
                last_robbery = datetime.strptime(last_robbery_raw, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                last_robbery = datetime.strptime(last_robbery_raw, "%Y-%m-%d %H:%M")
            if now - last_robbery < self.robbery_cooldown:
                remaining_time = last_robbery + self.robbery_cooldown - now
                remaining_seconds = int(remaining_time.total_seconds())
                remaining_hours, rem = divmod(remaining_seconds, 3600)
                remaining_minutes, remaining_secs = divmod(rem, 60)
                await interaction.response.send_message(embed=Embed(
                    title=title,
                    description=f"搶太兇會被盯上！再等 **{remaining_hours}** 小時 **{remaining_minutes}** 分 **{remaining_secs}** 秒才能再出手",
                    color=common.bot_error_color,
                ))
                return

        # 進入後續判斷：無論成敗皆寫入冷卻
        await common.mongo_storage.update_user_fields(userid, {self.robbery_interval_key: now.strftime("%Y-%m-%d %H:%M:%S")})

        robber_level = int(robber_data.get("level", 1))
        victim_level = int(victim_data.get("level", 1))
        success_rate = self.robbery_success_rate(robber_level, victim_level)
        success = random.random() * 100 < success_rate
        rate_text = f"{success_rate:.1f}".rstrip("0").rstrip(".")

        message = Embed(title=title, color=common.bot_color)
        message.add_field(name="搶劫者", value=f"<@{userid}> 等級:{robber_level}", inline=True)
        message.add_field(name="衰鬼", value=f"<@{member.id}> 等級:{victim_level}", inline=True)
        message.add_field(name="成功率", value=f"**{rate_text}%**", inline=True)

        if not success:
            message.add_field(name="結果", value="失手了！對方把蛋糕護得緊緊的……下次再來吧", inline=False)
            await interaction.response.send_message(embed=message)
            return

        steal_max = max(1, robber_level * self.robbery_cake_per_level)
        steal_amount = random.randint(1, steal_max)
        steal_result = await userdata_collection.find_one_and_update(
            {"_id": str(member.id), "cake": {"$gte": steal_amount}},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": -steal_amount}},
            upsert=False,
            return_document=common.ReturnDocument.AFTER,
        )
        if steal_result is None:
            message.add_field(name="結果", value=f"手伸進去了，結果口袋是空的……{common.cake_emoji}不知跑哪去了", inline=False)
            message.color = common.bot_error_color
            await interaction.response.send_message(embed=message)
            return

        try:
            await userdata_collection.update_one(
                {"_id": userid},
                {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": steal_amount}},
                upsert=True,
            )
        except Exception:
            await userdata_collection.update_one(
                {"_id": str(member.id)},
                {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": steal_amount}},
                upsert=True,
            )
            raise

        message.add_field(name="結果", value=f"得手！從 <@{member.id}> 那裡抱走了 **{steal_amount}** 塊{common.cake_emoji}！", inline=False)
        await interaction.response.send_message(embed=message)


async def setup(client:commands.Bot):
    await client.add_cog(Trade(client))
