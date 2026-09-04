from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
from dateutil.parser import parse
import json
import re
import discord
import time
import random
from typing import Optional
from collections import deque
import asyncio


class RedPacketSession:
    def __init__(self, creator_id: int, total_budget: int, people: int, amounts: list[int], ends_at: datetime, short_message: str | None = None):
        self.creator_id = creator_id
        self.total_budget = total_budget
        self.people = people
        self.short_message = short_message
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


class ServerItemHouse:
    """伺服器道具背包、狀態與使用效果。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.bag_key = "item_bag"
        self.status_key = "item_status"
        self.charge_key = "item_charges"
        self.bag_size = 99
        self.bag_page_size = 10
        self.win_cake_bonus_rate = 0.2
        self.robbery_success_bonus = 20.0
        self.speed_boots_cooldown = timedelta(minutes=10)
        self.slow_cooldown_multiplier = 2
        self.bodyguard_fail_cooldown = timedelta(days=1)
        self.blackjack_cheat_games = 20
        self.jade_bracelet_games = 50
        self.master_thief_robberies = 20
        self.rain_maker_cake_range = (1, 1200)
        self.magnet_steal_range = (500, 1000)
        self.strong_magnet_steal_range = (5000, 10000)
        self.status_anti_theft = "anti_theft"
        self.status_bodyguard = "bodyguard"
        self.status_lucky_glove = "lucky_glove"
        self.status_master_thief = "master_thief"
        self.status_slow = "slow"
        self.status_speed_boots = "speed_boots"
        self.status_camo_bag = "camo_bag"
        self.status_lightning_rod = "lightning_rod"
        self.status_amethyst = "amethyst_necklace"
        self.status_blackjack_cheat = "blackjack_cheat"
        self.status_jade_bracelet = "jade_bracelet"
        self.status_rain_maker = "rain_maker"
        self.charge_effect_keys = {self.status_blackjack_cheat, self.status_jade_bracelet}
        self.anti_theft_invalid_title = "你的防盜卡已失效"
        self.anti_theft_expired_reason = "已過期"
        self.anti_theft_milk_reason = "被 {actor_name} 的牛奶消除"
        self.status_labels = {
            self.status_anti_theft: "防盜卡",
            self.status_bodyguard: "保鏢卡",
            self.status_lucky_glove: "妙妙手套",
            self.status_master_thief: "神偷手套",
            self.status_slow: "遲緩",
            self.status_speed_boots: "神速靴",
            self.status_camo_bag: "迷彩包包",
            self.status_lightning_rod: "避雷針",
            self.status_amethyst: "紫水晶項鍊",
            self.status_blackjack_cheat: "21點作弊卡",
            self.status_jade_bracelet: "玉手鐲",
            self.status_rain_maker: "造雨機",
        }
        self.items = {
            "anti_theft_3": {
                "name": "防盜卡(3天)",
                "description": "一段時間內無法被其他玩家搶劫",
                "duration_days": 3,
                "use_kind": "self_status",
                "status_key": self.status_anti_theft,
            },
            "bodyguard_3": {
                "name": "保鏢卡(3天)",
                "description": "被搶劫時，如果對方搶劫失敗，搶劫指令冷卻時間變為一天",
                "duration_days": 3,
                "use_kind": "self_status",
                "status_key": self.status_bodyguard,
            },
            "milk": {
                "name": "牛奶",
                "description": "清除自己或一位玩家的所有狀態",
                "duration_days": 0,
                "use_kind": "milk",
                "need_target": True,
                "target_optional": True,
            },
            "blackjack_cheat": {
                "name": "21點作弊卡",
                "description": "在接下來的20場blackjack小遊戲，可以偷看第五張牌",
                "duration_days": 0,
                "use_kind": "self_charge",
                "status_key": self.status_blackjack_cheat,
                "charge_amount": self.blackjack_cheat_games,
            },
            "lucky_glove_7": {
                "name": "妙妙手套(7天)",
                "description": "搶劫時，成功率提高20%",
                "duration_days": 7,
                "use_kind": "self_status",
                "status_key": self.status_lucky_glove,
            },
            "master_thief_3": {
                "name": "神偷手套",
                "description": "在接下來的20次搶劫(無論是否成功)，偷竊數量範圍取最大值",
                "duration_days": 0,
                "use_kind": "self_charge",
                "status_key": self.status_master_thief,
                "charge_amount": self.master_thief_robberies,
            },
            "slow_potion_3": {
                "name": "遲緩藥水(3天)",
                "description": "賦予一位玩家遲緩效果，對有遲緩效果的人搶劫時，成功率提升20%，同時對方搶劫別人的成功率下降20%，並且對方每次搶劫後冷卻時間翻倍",
                "duration_days": 3,
                "use_kind": "target_status",
                "status_key": self.status_slow,
                "need_target": True,
            },
            "slow_spray_1": {
                "name": "遲緩噴霧(1天)",
                "description": "賦予一位玩家遲緩效果，對有遲緩效果的人搶劫時，成功率提升20%，同時對方搶劫別人的成功率下降20%，並且對方每次搶劫後冷卻時間翻倍。對象如果在語音房內，語音房的所有玩家都會獲得效果",
                "duration_days": 1,
                "use_kind": "slow_spray",
                "status_key": self.status_slow,
                "need_target": True,
            },
            "speed_boots_3": {
                "name": "神速靴(3天)",
                "description": "搶劫冷卻時間變為10分鐘",
                "duration_days": 3,
                "use_kind": "self_status",
                "status_key": self.status_speed_boots,
            },
            "jade_bracelet": {
                "name": "玉手鐲",
                "description": "在接下來的50場遊戲，獲勝時，蛋糕+20%",
                "duration_days": 0,
                "use_kind": "self_charge",
                "status_key": self.status_jade_bracelet,
                "charge_amount": self.jade_bracelet_games,
            },
            "amethyst_necklace_7": {
                "name": "紫水晶項鍊(7天)",
                "description": "在接下來的遊戲，獲勝時，蛋糕+20%",
                "duration_days": 7,
                "use_kind": "self_status",
                "status_key": self.status_amethyst,
            },
            "camo_bag_30": {
                "name": "迷彩包包(30天)",
                "description": "使用/bag指令時，其他人無法看到你的背包物品",
                "duration_days": 30,
                "use_kind": "self_status",
                "status_key": self.status_camo_bag,
            },
            "magnet": {
                "name": "磁鐵",
                "description": "只能在語音房使用，可以把語音房內其他人的蛋糕吸過來(500~1000)",
                "duration_days": 0,
                "use_kind": "magnet",
                "steal_range": self.magnet_steal_range,
                "voice_only": True,
            },
            "strong_magnet": {
                "name": "強力磁鐵",
                "description": "只能在語音房使用，可以把語音房內其他人的蛋糕吸過來(5000~10000)",
                "duration_days": 0,
                "use_kind": "magnet",
                "steal_range": self.strong_magnet_steal_range,
                "voice_only": True,
            },
            "heaven_punish": {
                "name": "天罰",
                "description": "摧毀一位玩家背包內的隨機一個道具(如果道具已疊加則為全部銷毀)",
                "duration_days": 0,
                "use_kind": "heaven_punish",
                "need_target": True,
            },
            "lightning_rod_30": {
                "name": "避雷針(30天)",
                "description": "反彈天罰給道具使用者",
                "duration_days": 30,
                "use_kind": "self_status",
                "status_key": self.status_lightning_rod,
            },
            "rain_maker_7": {
                "name": "造雨機(7天)",
                "description": "賦予狀態:在周圍下起蛋糕雨。你在語音房的期間，你與其他同語音的人每隔一段時間都會拿到蛋糕(1~1200)",
                "duration_days": 7,
                "use_kind": "self_status",
                "status_key": self.status_rain_maker,
            },
        }

    def panel_item_guides(self) -> list[dict]:
        """
        互動面板首頁用的道具說明。

        Returns:
            guides (list): "[{'name': '防盜卡(3天)', 'kind_label': '狀態 3天'}]"
        """
        guides = []
        for item in self.items.values():
            duration_days = int(item.get("duration_days") or 0)
            if duration_days > 0:
                kind_label = f"狀態 {duration_days}天"
            elif item.get("use_kind") == "self_charge":
                charge_amount = int(item.get("charge_amount") or 0)
                kind_label = f"{charge_amount}次" if item.get("status_key") == self.status_master_thief else f"{charge_amount}場"
            else:
                kind_label = "一次性"
            guides.append({
                "name": item["name"],
                "description": item["description"],
                "kind_label": kind_label,
            })
        return guides

    def parse_time(self, raw) -> datetime | None:
        """
        解析狀態到期時間。

        Args:
            raw: "2026-09-04 15:00:00"

        Returns:
            parsed (datetime | None): "2026-09-04 15:00:00"
        """
        if isinstance(raw, datetime):
            return raw.replace(tzinfo=None)
        if not raw:
            return None
        try:
            return datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return parse(str(raw)).replace(tzinfo=None)
            except (ValueError, TypeError):
                return None

    def remaining_hours_text(self, expires_at: datetime, now: datetime) -> str:
        """
        狀態剩餘時間文字。

        Args:
            expires_at (datetime): "2026-09-04 15:00:00"
            now (datetime): "2026-09-01 15:00:00"

        Returns:
            text (str): "剩餘 **72** 小時"
        """
        seconds = (expires_at - now).total_seconds()
        if seconds <= 0:
            return "剩餘 **0** 小時"
        hours = max(1, int((seconds + 3599) // 3600))
        return f"剩餘 **{hours}** 小時"

    def normalize_bag(self, user_data: dict) -> list:
        """
        把背包補齊成固定 99 格。

        Args:
            user_data (dict): "{'item_bag': []}"

        Returns:
            bag (list): "[{'item_id': 'milk', 'count': 1}, None]"
        """
        raw = user_data.get(self.bag_key)
        bag = [None] * self.bag_size
        if not isinstance(raw, list):
            user_data[self.bag_key] = bag
            return bag
        for index in range(min(len(raw), self.bag_size)):
            entry = raw[index]
            if isinstance(entry, dict) and entry.get("item_id") and int(entry.get("count") or 0) > 0:
                bag[index] = {"item_id": str(entry["item_id"]), "count": int(entry["count"])}
        user_data[self.bag_key] = bag
        return bag

    def first_empty_index(self, bag: list) -> Optional[int]:
        """
        第一個空格。

        Args:
            bag (list): "[None, {'item_id': 'milk', 'count': 1}]"

        Returns:
            index (int | None): "0"
        """
        for index, entry in enumerate(bag):
            if entry is None:
                return index
        return None

    def can_receive_on_bag(self, bag: list, item_id: str) -> bool:
        """
        此背包能否再收下此道具（可疊加或有空格）。

        Args:
            bag (list): "[{'item_id': 'milk', 'count': 1}]"
            item_id (str): "milk"

        Returns:
            ok (bool): "True"
        """
        for entry in bag:
            if isinstance(entry, dict) and entry.get("item_id") == item_id:
                return True
        return self.first_empty_index(bag) is not None

    def count_item_on_bag(self, bag: list, item_id: str) -> int:
        """
        統計某道具數量。

        Args:
            bag (list): "[{'item_id': 'milk', 'count': 2}]"
            item_id (str): "milk"

        Returns:
            count (int): "2"
        """
        total = 0
        for entry in bag:
            if isinstance(entry, dict) and entry.get("item_id") == item_id:
                total += int(entry.get("count") or 0)
        return total

    def occupied_indexes(self, bag: list) -> list[int]:
        """
        有道具的格子。

        Args:
            bag (list): "[{'item_id': 'milk', 'count': 1}, None]"

        Returns:
            indexes (list): "[0]"
        """
        return [index for index, entry in enumerate(bag) if isinstance(entry, dict)]

    def item_display_name(self, item_id: str) -> str:
        """
        道具顯示名稱。

        Args:
            item_id (str): "anti_theft_3"

        Returns:
            name (str): "防盜卡(3天)"
        """
        item = self.items.get(item_id) or {}
        return str(item.get("name") or item_id)

    def item_description(self, item_id: str) -> str:
        """
        道具效果說明。

        Args:
            item_id (str): "milk"

        Returns:
            text (str): "清除自己或一位玩家的所有狀態"
        """
        item = self.items.get(item_id) or {}
        return str(item.get("description") or "未知道具")

    def prune_status_in_data(self, user_data: dict) -> bool:
        """
        清掉過期狀態，並把場數效果從狀態裡搬出去。

        Args:
            user_data (dict): "{'item_status': {}}"

        Returns:
            changed (bool): "True"
        """
        status = user_data.get(self.status_key)
        if not isinstance(status, dict):
            user_data[self.status_key] = {}
            status = user_data[self.status_key]
        charges = user_data.get(self.charge_key)
        if not isinstance(charges, dict):
            user_data[self.charge_key] = {}
            charges = user_data[self.charge_key]
        now = datetime.now()
        changed = False
        for key in list(self.charge_effect_keys):
            if key not in status:
                continue
            charges[key] = status.pop(key)
            changed = True
        for key in list(status.keys()):
            entry = status[key]
            if not isinstance(entry, dict):
                del status[key]
                changed = True
                continue
            expires = self.parse_time(entry.get("expires_at"))
            if expires is None or expires <= now:
                del status[key]
                changed = True
        for key in list(charges.keys()):
            entry = charges[key]
            if not isinstance(entry, dict) or int(entry.get("remaining") or 0) <= 0:
                del charges[key]
                changed = True
        return changed

    def has_status_in_data(self, user_data: dict, status_key: str) -> bool:
        """
        文件上是否仍有此狀態。

        Args:
            user_data (dict): "{'item_status': {'anti_theft': {}}}"
            status_key (str): "anti_theft"

        Returns:
            active (bool): "True"
        """
        self.prune_status_in_data(user_data)
        status = user_data.get(self.status_key)
        return isinstance(status, dict) and status_key in status

    def anti_theft_is_expired_in_data(self, user_data: dict) -> bool:
        """
        文件上的防盜卡是否已到期或無效，這次 prune 會清掉。

        Args:
            user_data (dict): "{'item_status': {'anti_theft': {'expires_at': '2026-01-01 00:00:00'}}}"

        Returns:
            expired (bool): "True"
        """
        status = user_data.get(self.status_key)
        if not isinstance(status, dict):
            return False
        entry = status.get(self.status_anti_theft)
        if not isinstance(entry, dict):
            return False
        expires = self.parse_time(entry.get("expires_at"))
        return expires is None or expires <= datetime.now()

    def robbery_cooldown_of(self, robber_data: dict, base_cooldown: timedelta, forced_seconds: int | None = None) -> timedelta:
        """
        依神速靴、遲緩與保鏢卡失敗懲罰計算搶劫冷卻。

        Args:
            robber_data (dict): "{'item_status': {}}"
            base_cooldown (timedelta): "1:00:00"
            forced_seconds (int | None): "86400"

        Returns:
            cooldown (timedelta): "0:10:00"
        """
        if forced_seconds is not None and forced_seconds > 0:
            return timedelta(seconds=int(forced_seconds))
        cooldown = self.speed_boots_cooldown if self.has_status_in_data(robber_data, self.status_speed_boots) else base_cooldown
        if self.has_status_in_data(robber_data, self.status_slow):
            cooldown = cooldown * self.slow_cooldown_multiplier
        return cooldown

    def has_master_thief_effect(self, user_data: dict) -> bool:
        """
        是否仍有神偷手套效果（舊版時效狀態或新版次數）。

        Args:
            user_data (dict): "{'item_status': {}, 'item_charges': {}}"

        Returns:
            active (bool): "True"
        """
        if self.has_status_in_data(user_data, self.status_master_thief):
            return True
        return self.charge_remaining_in_data(user_data, self.status_master_thief) > 0

    async def rain_maker_channel_bonus(self, member_ids: list[str]) -> int:
        """
        語音房內每位持有造雨機狀態的人各判定一次，回傳加總後該房每人應加的蛋糕。

        Args:
            member_ids (list): "['4108']"

        Returns:
            bonus (int): "500"
        """
        if not member_ids:
            return 0
        total_bonus = 0
        low, high = self.rain_maker_cake_range
        for member_id in member_ids:
            user_data = await self.load_user(member_id)
            if self.has_status_in_data(user_data, self.status_rain_maker):
                total_bonus += random.randint(low, high)
        return total_bonus

    def charge_remaining_in_data(self, user_data: dict, charge_key: str) -> int:
        """
        剩餘場數。

        Args:
            user_data (dict): "{'item_charges': {'jade_bracelet': {'remaining': 50}}}"
            charge_key (str): "jade_bracelet"

        Returns:
            remaining (int): "50"
        """
        self.prune_status_in_data(user_data)
        charges = user_data.get(self.charge_key)
        if not isinstance(charges, dict):
            return 0
        entry = charges.get(charge_key)
        if not isinstance(entry, dict):
            return 0
        return max(0, int(entry.get("remaining") or 0))

    def add_timed_status(self, user_data: dict, status_key: str, days: int) -> None:
        """
        疊加持續狀態時數。

        Args:
            user_data (dict): "{'item_status': {}}"
            status_key (str): "anti_theft"
            days (int): "3"
        """
        self.prune_status_in_data(user_data)
        status = user_data.setdefault(self.status_key, {})
        now = datetime.now()
        extra = timedelta(days=days)
        current = status.get(status_key) if isinstance(status.get(status_key), dict) else None
        base = now
        if current is not None:
            expires = self.parse_time(current.get("expires_at"))
            if expires is not None and expires > now:
                base = expires
        status[status_key] = {"expires_at": (base + extra).strftime("%Y-%m-%d %H:%M:%S")}

    def add_charge_status(self, user_data: dict, charge_key: str, amount: int) -> None:
        """
        疊加場數效果，不寫入狀態。

        Args:
            user_data (dict): "{'item_charges': {}}"
            charge_key (str): "blackjack_cheat"
            amount (int): "20"
        """
        self.prune_status_in_data(user_data)
        charges = user_data.setdefault(self.charge_key, {})
        current = charges.get(charge_key) if isinstance(charges.get(charge_key), dict) else {}
        remaining = int(current.get("remaining") or 0)
        charges[charge_key] = {"remaining": remaining + amount}

    def consume_charge_in_data(self, user_data: dict, charge_key: str, amount: int = 1) -> bool:
        """
        消耗場數效果。

        Args:
            user_data (dict): "{'item_charges': {'blackjack_cheat': {'remaining': 20}}}"
            charge_key (str): "blackjack_cheat"
            amount (int): "1"

        Returns:
            consumed (bool): "True"
        """
        remaining = self.charge_remaining_in_data(user_data, charge_key)
        if remaining <= 0:
            return False
        charges = user_data.setdefault(self.charge_key, {})
        leftover = remaining - amount
        if leftover <= 0:
            charges.pop(charge_key, None)
        else:
            charges[charge_key] = {"remaining": leftover}
        return True

    def apply_win_cake_bonus(self, user_data: dict, profit: int) -> int:
        """
        依玉手鐲／紫水晶項鍊計算獲勝蛋糕加成。

        Args:
            user_data (dict): "{'item_status': {}}"
            profit (int): "100"

        Returns:
            bonus (int): "20"
        """
        if profit <= 0:
            return 0
        stacks = 0
        if self.has_status_in_data(user_data, self.status_amethyst):
            stacks += 1
        if self.charge_remaining_in_data(user_data, self.status_jade_bracelet) > 0:
            stacks += 1
        if stacks <= 0:
            return 0
        return int(profit * self.win_cake_bonus_rate * stacks)

    def format_status_text(self, user_data: dict) -> str:
        """
        /info 狀態欄文字。

        Args:
            user_data (dict): "{'item_status': {}}"

        Returns:
            text (str): "防盜卡:剩餘 **72** 小時"
        """
        self.prune_status_in_data(user_data)
        now = datetime.now()
        lines = []
        status = user_data.get(self.status_key)
        if isinstance(status, dict):
            for key, entry in status.items():
                if key in self.charge_effect_keys or not isinstance(entry, dict):
                    continue
                expires = self.parse_time(entry.get("expires_at"))
                if expires is None:
                    continue
                label = self.status_labels.get(key, key)
                lines.append(f"{label}:{self.remaining_hours_text(expires, now)}")
        return "\n".join(lines)

    def format_win_bonus_line(self, bonus: int) -> str:
        """
        獲勝加成顯示。

        Args:
            bonus (int): "20"

        Returns:
            text (str): "\\n道具加成：**+20**塊<:cake:1>"
        """
        if bonus <= 0:
            return ""
        return f"\n道具加成：**+{bonus}**塊{common.cake_emoji}"

    def format_jade_bracelet_charge_text(self, remaining: int) -> str:
        """
        遊戲結算時玉手鐲剩餘場數提示。

        Args:
            remaining (int): "49"

        Returns:
            text (str): "本次已消耗 1 場，剩餘 **49** 場"
        """
        return f"本次已消耗 1 場，剩餘 **{remaining}** 場"

    async def load_user(self, user_id: str) -> dict:
        """
        讀取使用者並清掉過期狀態。

        Args:
            user_id (str): "410847926236086272"

        Returns:
            user_data (dict): "{'cake': 0, 'item_bag': []}"
        """
        user_data = await common.mongo_storage.ensure_user_document(str(user_id))
        self.normalize_bag(user_data)
        expired_anti_theft = self.anti_theft_is_expired_in_data(user_data)
        if self.prune_status_in_data(user_data):
            await common.mongo_storage.update_user_fields(
                str(user_id),
                {
                    self.status_key: user_data.get(self.status_key, {}),
                    self.charge_key: user_data.get(self.charge_key, {}),
                },
            )
            if expired_anti_theft:
                await self.notify_anti_theft_expired(user_id)
        return user_data

    async def resolve_user(self, user_id: str) -> discord.User | None:
        """
        用 user_id 取得 Discord 使用者，快取沒有再向 API 抓。

        Args:
            user_id (str): "410847926236086272"

        Returns:
            user (discord.User | None): "使用者"
        """
        try:
            parsed_id = int(user_id)
        except (TypeError, ValueError):
            return None
        user = self.bot.get_user(parsed_id)
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(parsed_id)
        except (discord.HTTPException, discord.NotFound):
            return None

    async def send_anti_theft_invalid_dm(self, user, reason_text: str) -> None:
        """
        私訊玩家防盜卡已失效；關閉私訊或失敗時略過。

        Args:
            user: "Discord 使用者"
            reason_text (str): "已過期"
        """
        if user is None:
            return
        embed = Embed(
            title=self.anti_theft_invalid_title,
            description=f"原因：{reason_text}",
            color=common.bot_color,
        )
        try:
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            return

    async def notify_anti_theft_expired(self, user_id: str) -> None:
        """
        防盜卡因過期被清除時私訊玩家。

        Args:
            user_id (str): "410847926236086272"
        """
        user = await self.resolve_user(user_id)
        await self.send_anti_theft_invalid_dm(user, self.anti_theft_expired_reason)

    async def save_bag_and_status(self, user_id: str, user_data: dict) -> None:
        """
        寫回背包與狀態。

        Args:
            user_id (str): "410847926236086272"
            user_data (dict): "{'item_bag': [], 'item_status': {}}"
        """
        await common.mongo_storage.update_user_fields(
            str(user_id),
            {
                self.bag_key: user_data.get(self.bag_key) or [None] * self.bag_size,
                self.status_key: user_data.get(self.status_key) or {},
                self.charge_key: user_data.get(self.charge_key) or {},
            },
        )

    async def can_receive(self, user_id: str, item_id: str) -> bool:
        """
        此玩家背包能否再收下此道具。

        Args:
            user_id (str): "410847926236086272"
            item_id (str): "milk"

        Returns:
            ok (bool): "True"
        """
        if item_id not in self.items:
            return False
        user_data = await self.load_user(user_id)
        return self.can_receive_on_bag(self.normalize_bag(user_data), item_id)

    async def count_item(self, user_id: str, item_id: str) -> int:
        """
        讀取持有數量。

        Args:
            user_id (str): "410847926236086272"
            item_id (str): "milk"

        Returns:
            count (int): "2"
        """
        user_data = await self.load_user(user_id)
        return self.count_item_on_bag(self.normalize_bag(user_data), item_id)

    def put_items_on_bag(self, bag: list, item_id: str, quantity: int) -> bool:
        """
        把道具疊進背包。

        Args:
            bag (list): "[None]"
            item_id (str): "milk"
            quantity (int): "2"

        Returns:
            ok (bool): "True"
        """
        if quantity <= 0 or item_id not in self.items:
            return False
        for entry in bag:
            if isinstance(entry, dict) and entry.get("item_id") == item_id:
                entry["count"] = int(entry.get("count") or 0) + quantity
                return True
        empty_index = self.first_empty_index(bag)
        if empty_index is None:
            return False
        bag[empty_index] = {"item_id": item_id, "count": quantity}
        return True

    def take_items_from_bag(self, bag: list, item_id: str, quantity: int) -> bool:
        """
        從背包扣掉道具。

        Args:
            bag (list): "[{'item_id': 'milk', 'count': 2}]"
            item_id (str): "milk"
            quantity (int): "1"

        Returns:
            ok (bool): "True"
        """
        if quantity <= 0:
            return False
        leftover = quantity
        for index, entry in enumerate(bag):
            if not isinstance(entry, dict) or entry.get("item_id") != item_id:
                continue
            have = int(entry.get("count") or 0)
            if have <= leftover:
                leftover -= have
                bag[index] = None
            else:
                entry["count"] = have - leftover
                leftover = 0
            if leftover <= 0:
                return True
        return False

    async def add_items(self, user_id: str, item_id: str, quantity: int) -> bool:
        """
        發放道具到背包。

        Args:
            user_id (str): "410847926236086272"
            item_id (str): "milk"
            quantity (int): "2"

        Returns:
            ok (bool): "True"
        """
        if item_id not in self.items or quantity <= 0:
            return False
        async with self.lock:
            user_data = await self.load_user(user_id)
            bag = self.normalize_bag(user_data)
            if not self.put_items_on_bag(bag, item_id, quantity):
                return False
            await self.save_bag_and_status(user_id, user_data)
            return True

    async def remove_items(self, user_id: str, item_id: str, quantity: int) -> bool:
        """
        從背包移除道具。

        Args:
            user_id (str): "410847926236086272"
            item_id (str): "milk"
            quantity (int): "1"

        Returns:
            ok (bool): "True"
        """
        if item_id not in self.items or quantity <= 0:
            return False
        async with self.lock:
            user_data = await self.load_user(user_id)
            bag = self.normalize_bag(user_data)
            if self.count_item_on_bag(bag, item_id) < quantity:
                return False
            if not self.take_items_from_bag(bag, item_id, quantity):
                return False
            await self.save_bag_and_status(user_id, user_data)
            return True

    async def build_bag_embed(self, user_id: str, page: int) -> Embed:
        """
        組出背包某一頁。

        Args:
            user_id (str): "410847926236086272"
            page (int): "0"

        Returns:
            embed (Embed): Embed(...)
        """
        user_data = await self.load_user(user_id)
        bag = self.normalize_bag(user_data)
        max_page = (self.bag_size - 1) // self.bag_page_size
        page = max(0, min(page, max_page))
        start = page * self.bag_page_size
        end = min(start + self.bag_page_size, self.bag_size)
        used = len(self.occupied_indexes(bag))
        embed = Embed(
            title="Natalie 背包",
            description=f"共 {self.bag_size} 格，已使用 **{used}** 格。第 **{page + 1}**／**{max_page + 1}** 頁。\n使用 `/bag 編號` 使用道具；需要對象時加上 `/bag 編號:@玩家`。",
            color=common.bot_color,
        )
        for index in range(start, end):
            entry = bag[index]
            slot_label = index + 1
            if not isinstance(entry, dict):
                embed.add_field(name=f"[{slot_label}] （空）", value="—", inline=False)
                continue
            item_id = str(entry.get("item_id") or "")
            count = int(entry.get("count") or 0)
            embed.add_field(
                name=f"[{slot_label}] {self.item_display_name(item_id)}  x{count}",
                value=self.item_description(item_id),
                inline=False,
            )
        return embed

    def voice_members(self, member: discord.Member | None) -> list[discord.Member]:
        """
        語音房內的非機器人成員。

        Args:
            member (discord.Member | None): "某位玩家"

        Returns:
            members (list): "[Member(...)]"
        """
        if member is None:
            return []
        voice = getattr(member, "voice", None)
        if voice is None or voice.channel is None:
            return []
        return [person for person in voice.channel.members if not person.bot]

    async def transfer_cake(self, from_id: str, to_id: str, amount: int) -> int:
        """
        把蛋糕從一人轉到另一人，實際數量可能較少。

        Args:
            from_id (str): "1234"
            to_id (str): "4108"
            amount (int): "800"

        Returns:
            moved (int): "800"
        """
        if amount <= 0 or from_id == to_id:
            return 0
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        victim = await common.mongo_storage.ensure_user_document(from_id)
        take = min(amount, int(victim.get("cake", 0) or 0))
        if take <= 0:
            return 0
        steal_result = await userdata_collection.find_one_and_update(
            {"_id": from_id, "cake": {"$gte": take}},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": -take}},
            upsert=False,
            return_document=common.ReturnDocument.AFTER,
        )
        if steal_result is None:
            return 0
        try:
            await userdata_collection.update_one(
                {"_id": to_id},
                {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": take}},
                upsert=True,
            )
        except Exception:
            await userdata_collection.update_one(
                {"_id": from_id},
                {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": take}},
                upsert=True,
            )
            raise
        return take

    def take_random_stack(self, bag: list) -> str | None:
        """
        從背包摧毀一個隨機堆疊。

        Args:
            bag (list): "[{'item_id': 'milk', 'count': 2}]"

        Returns:
            item_name (str | None): "牛奶 x2"
        """
        indexes = self.occupied_indexes(bag)
        if not indexes:
            return None
        index = random.choice(indexes)
        entry = bag[index]
        item_id = str(entry.get("item_id") or "")
        count = int(entry.get("count") or 0)
        bag[index] = None
        name = self.item_display_name(item_id)
        return f"{name} x{count}" if count > 1 else name

    async def use_slot(self, user_id: str, slot: int, target: discord.Member | None, actor: discord.Member) -> tuple[bool, str]:
        """
        使用背包某一格。

        Args:
            user_id (str): "410847926236086272"
            slot (int): "1"
            target (discord.Member | None): "要作用的玩家"
            actor (discord.Member): "指令使用者"

        Returns:
            result (tuple): "(True, '使用成功')"
        """
        if slot < 1 or slot > self.bag_size:
            return False, f"格子編號須為 **1**～**{self.bag_size}**。"
        async with self.lock:
            user_data = await self.load_user(user_id)
            bag = self.normalize_bag(user_data)
            entry = bag[slot - 1]
            if not isinstance(entry, dict):
                return False, "該格沒有物品。"
            item_id = str(entry.get("item_id") or "")
            item = self.items.get(item_id)
            if item is None:
                return False, "未知的道具，無法使用。"
            need_target = bool(item.get("need_target"))
            target_optional = bool(item.get("target_optional"))
            if need_target and target is None and not target_optional:
                return False, f"使用 **{item['name']}** 需要指定對象：`/bag {slot}:@玩家`"
            if target is not None and target.bot:
                return False, "不能對機器人使用道具。"
            if item.get("voice_only"):
                voice_people = self.voice_members(actor)
                if actor not in voice_people:
                    return False, f"**{item['name']}** 只能在語音房內使用。"
            if item.get("status_key") == self.status_anti_theft and any(role.id == common.super_vip_id for role in actor.roles):
                return False, f"至寶本身就不會被搶劫，**{item['name']}** 用不到喔。"
            if int(entry.get("count") or 0) <= 0:
                return False, "該格沒有物品。"
            bag[slot - 1]["count"] = int(entry["count"]) - 1
            if bag[slot - 1]["count"] <= 0:
                bag[slot - 1] = None
            ok, message = await self.apply_item_effect(item_id, item, user_id, user_data, target, actor)
            if not ok:
                return False, message
            await self.save_bag_and_status(user_id, user_data)
            return True, message

    async def apply_item_effect(self, item_id: str, item: dict, user_id: str, user_data: dict, target: discord.Member | None, actor: discord.Member) -> tuple[bool, str]:
        """
        套用道具效果。呼叫端已預扣 1 個。

        Args:
            item_id (str): "milk"
            item (dict): "{'use_kind': 'milk'}"
            user_id (str): "410847926236086272"
            user_data (dict): "{'item_status': {}}"
            target (discord.Member | None): "對象"
            actor (discord.Member): "使用者"

        Returns:
            result (tuple): "(True, '使用成功')"
        """
        use_kind = item.get("use_kind")
        name = item["name"]
        if use_kind == "self_status":
            self.add_timed_status(user_data, item["status_key"], int(item["duration_days"]))
            return True, f"使用了 **{name}**，效果已套用到自己身上。"
        if use_kind == "self_charge":
            self.add_charge_status(user_data, item["status_key"], int(item["charge_amount"]))
            remaining = self.charge_remaining_in_data(user_data, item["status_key"])
            unit = "次" if item["status_key"] == self.status_master_thief else "場"
            return True, f"使用了 **{name}**，目前剩餘 **{remaining}** {unit}。"
        if use_kind == "target_status":
            target_member = target or actor
            target_data = user_data if str(target_member.id) == user_id else await self.load_user(str(target_member.id))
            self.add_timed_status(target_data, item["status_key"], int(item["duration_days"]))
            if str(target_member.id) != user_id:
                await self.save_bag_and_status(str(target_member.id), target_data)
            who = "自己" if target_member.id == actor.id else f"<@{target_member.id}>"
            return True, f"使用了 **{name}**，已賦予 {who} 遲緩效果。"
        if use_kind == "slow_spray":
            target_member = target or actor
            affected = [target_member]
            for person in self.voice_members(target_member):
                if person.id not in {member.id for member in affected}:
                    affected.append(person)
            for person in affected:
                person_data = user_data if str(person.id) == user_id else await self.load_user(str(person.id))
                self.add_timed_status(person_data, self.status_slow, int(item["duration_days"]))
                if str(person.id) != user_id:
                    await self.save_bag_and_status(str(person.id), person_data)
            mentions = "、".join(f"<@{person.id}>" for person in affected)
            return True, f"使用了 **{name}**，已賦予 {mentions} 遲緩效果。"
        if use_kind == "milk":
            target_member = target or actor
            target_data = user_data if str(target_member.id) == user_id else await self.load_user(str(target_member.id))
            had_anti_theft = self.has_status_in_data(target_data, self.status_anti_theft)
            target_data[self.status_key] = {}
            if str(target_member.id) != user_id:
                await self.save_bag_and_status(str(target_member.id), target_data)
            if had_anti_theft:
                await self.send_anti_theft_invalid_dm(
                    target_member,
                    self.anti_theft_milk_reason.format(actor_name=actor.display_name),
                )
            who = "自己" if target_member.id == actor.id else f"<@{target_member.id}>"
            return True, f"使用了 **{name}**，已清除 {who} 的所有狀態。"
        if use_kind == "magnet":
            low, high = item["steal_range"]
            others = [person for person in self.voice_members(actor) if person.id != actor.id]
            if not others:
                self.put_items_on_bag(self.normalize_bag(user_data), item_id, 1)
                return False, f"**{name}** 需要語音房裡還有其他玩家。"
            lines = []
            total = 0
            for person in others:
                taken = await self.transfer_cake(str(person.id), user_id, random.randint(low, high))
                if taken <= 0:
                    continue
                total += taken
                lines.append(f"<@{person.id}> **{taken}**塊{common.cake_emoji}")
            if total <= 0:
                return True, f"使用了 **{name}**，但語音房裡的人身上都沒有蛋糕。"
            detail = "\n".join(lines)
            return True, f"使用了 **{name}**，從語音房吸來 **{total}**塊{common.cake_emoji}：\n{detail}"
        if use_kind == "heaven_punish":
            if target is None:
                self.put_items_on_bag(self.normalize_bag(user_data), item_id, 1)
                return False, f"使用 **{name}** 需要指定對象：`/bag 編號:@玩家`"
            if str(target.id) == user_id:
                destroyed = self.take_random_stack(self.normalize_bag(user_data))
                if destroyed is None:
                    return True, f"使用了 **{name}**，但你的背包已經沒有其他道具。"
                return True, f"使用了 **{name}**，摧毀了自己的 **{destroyed}**。"
            victim_data = await self.load_user(str(target.id))
            if self.has_status_in_data(victim_data, self.status_lightning_rod):
                destroyed = self.take_random_stack(self.normalize_bag(user_data))
                if destroyed is None:
                    return True, f"使用了 **{name}**，被 <@{target.id}> 的避雷針反彈，但你的背包是空的。"
                return True, f"使用了 **{name}**，被 <@{target.id}> 的避雷針反彈，摧毀了你的 **{destroyed}**。"
            destroyed = self.take_random_stack(self.normalize_bag(victim_data))
            if destroyed is None:
                self.put_items_on_bag(self.normalize_bag(user_data), item_id, 1)
                return False, f"<@{target.id}> 的背包是空的，天罰沒有東西可以摧毀。"
            await self.save_bag_and_status(str(target.id), victim_data)
            return True, f"使用了 **{name}**，摧毀了 <@{target.id}> 的 **{destroyed}**。"
        self.put_items_on_bag(self.normalize_bag(user_data), item_id, 1)
        return False, "這個道具目前無法使用。"


class BagPageView(discord.ui.View):
    """背包上一頁／下一頁。"""

    def __init__(self, house: ServerItemHouse, owner_id: int, page: int):
        super().__init__(timeout=180.0)
        self.house = house
        self.owner_id = owner_id
        self.page = page
        self.max_page = (house.bag_size - 1) // house.bag_page_size
        self.prev_button.disabled = page <= 0
        self.next_button.disabled = page >= self.max_page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(embed=Embed(title="Natalie 背包", description=random.choice([
            "你不要亂翻別人的背包!!",
            "把手拿開，這不是你的!!",
            "偷看別人包包是很沒品的!!",
        ]), color=common.bot_error_color), ephemeral=True)
        return False

    async def show_page(self, interaction: discord.Interaction, page: int) -> None:
        """
        切換背包頁並更新按鈕。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            page (int): "1"
        """
        self.page = max(0, min(page, self.max_page))
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.max_page
        embed = await self.house.build_bag_embed(str(self.owner_id), self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="上一頁", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, self.page - 1)

    @discord.ui.button(label="下一頁", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, self.page + 1)


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
        self.animation_color_code_whitelist = [
            "823967449149603861", #小八
            "277828424872230912", #七色
            "1190971324647092237", #泥巴
            "543126405978783765", #一ㄈ
            "399210985304489985", #小Q
            "472308372616773632", #tako
            "587934995063111681", #xu6
        ]
        self.vip_retain_days = 30  # 取消 Boost 後仍保留 VIP 的天數
        self.message_audit_content_limit = 1000  # 訊息審核 embed 內容字數上限
        self.message_audit_max_attachments = 10  # 訊息審核最多附檔數量
        self.invite_link_pattern = re.compile(
            r"(?:https?://)?(?:www\.)?"
            r"(?:discord(?:app)?\.com/invite|discord\.gg)/"
            r"([a-zA-Z0-9-]{2,32})",
            re.IGNORECASE,
        )
        self.svip_intro = (
            f"至寶是每日任務結算時，{common.marshmallow_emoji}棉花糖數量最多的成員所獲得的榮譽稱號。\n"
            "持有期間可享有以下特權："
        )
        self.svip_privilege_lines = [
            "身份組獨立顯示",
            "`/cake_give` 不會被偷吃蛋糕",
            "可自由選擇動態顏色身份組",
            "至寶身份組的動態顏色覺得太醜可以隨時換",
            "語音活躍獎勵額外加成",
            "群主不定期送禮",
            "可以使用外部音效版",
            "可以選擇是否查看語音頻道日誌（`/show_voice_log`）",
            "可以選擇是否隱藏自己的語音頻道足跡（`/hide_voice_trace`）",
            "別人無法掠奪你的蛋糕"
        ]
        self.server_item_house = ServerItemHouse(client)
        client.server_item_house = self.server_item_house

    @staticmethod
    def compute_red_packet_amounts(total: int, people: int) -> list[int]:
        """依規則切分紅包金額（整數蛋糕），回傳長度為 people 的清單，加總為 total。"""
        if people < 3 or people > 15:
            raise ValueError("人數需在 3～15 之間")
        if total < 1:
            raise ValueError("總金額須為正整數")
        if total < people:
            raise ValueError(f"總金額至少需等於人數（每人至少 1 塊{common.cake_emoji}）")
        cuts = sorted(random.sample(range(1, total), people - 1))
        positions = [0] + cuts + [total]
        parts = [positions[index + 1] - positions[index] for index in range(people)]
        random.shuffle(parts)
        return parts

    @app_commands.command(name = "info", description = "關於Natalie...")
    async def info(self,interaction):
        userid = str(interaction.user.id)
        user_data = await self.server_item_house.load_user(userid)
        cake = int(user_data.get("cake", 0))

        userlevel = await common.LevelSystem().read_info(userid)
        message = Embed(title="我是Natalie!",description="你好!我是Natalie!\n你可以在這裡查看個人資料及指令表。",color=common.bot_color)
        cake_emoji = common.cake_emoji
        cake_commands_list = [
            f"/eat 餵食Natalie一些{cake_emoji} (1 cake = 1 exp)",
            f"/cake_give 給予他人{cake_emoji}",
            "/red_packet 發紅包(蛋糕)",
            "/robbery 掠奪別人的蛋糕",
            "/shop 商店",
            "/bag 查看或使用背包道具",
        ]
        game_commands_list = [
            "/mining_info 挖礦小遊戲資訊",
            "/blackjack 21點遊戲",
            "/poker 撲克牌比大小",
            "/poker_statistics 撲克牌比大小個人統計",
            "/squid_rps 魷魚遊戲猜拳",
            "/squid_rps_setdifficulty 設定魷魚猜拳難度"
        ]
        appearance_commands_list = [
            "/set_color 更換ID的顏色(靜態)",
            "/set_animation_color 更換ID的顏色(動態)",
            "/redeem_member_role 兌換自訂稱號(每月一次)"
        ]
        other_commands_list = [
            "/quest 查看每日任務",
            "/check_sevencolor_restday 確認七色有沒有休假",
            "/create_bid 建立競標交易",
            "/warnlist 查看警告紀錄"
        ]
        #如果等級>=5 且沒有在 抽獎仔/VIP 身分內，則顯示指令
        if userlevel.level >= 5 and all(role.id not in [621764669929160715, common.vip_role_id] for role in interaction.user.roles):
            other_commands_list.append("/giveaway_join 加入抽獎頻道")
        leaderboard_commands_list = [
            "/level_leaderboard 等級排行榜",
            "/voice_leaderboard 語音活躍排行榜",
            "/blackjack_leaderboard 21點勝率排行榜",
            "/poker_leaderboard 撲克牌勝率排行榜",
            "/squid_rps_leaderboard 魷魚猜拳勝率排行榜",
            "/cake_leaderboard 蛋糕排行榜"
        ]

        message.add_field(name="個人資料",value=f"等級:**{userlevel.level}**  經驗值:**{userlevel.level_exp}**/**{userlevel.level_next_exp}**\n你有**{cake}**塊{cake_emoji}",inline=False)
        status_text = self.server_item_house.format_status_text(user_data)
        if status_text:
            message.add_field(name="狀態", value=status_text, inline=False)
        message.add_field(name="蛋糕", value="\n".join(cake_commands_list), inline=False)
        message.add_field(name="遊戲", value="\n".join(game_commands_list), inline=False)
        message.add_field(name="外觀", value="\n".join(appearance_commands_list), inline=False)
        message.add_field(name="其他", value="\n".join(other_commands_list), inline=False)
        message.add_field(name="排行榜", value="\n".join(leaderboard_commands_list), inline=False)
        await interaction.response.send_message(embed=message)

    @app_commands.command(name = "eat", description = "餵食Natalie!")
    @app_commands.describe(eat_cake="要餵食的蛋糕數量，1蛋糕=1經驗值")
    @app_commands.rename(eat_cake="數量")
    async def eat(self,interaction,eat_cake: int):
        # 檢查餵食數量是否有效
        if eat_cake <= 0:
            await interaction.response.send_message(embed=Embed(title='餵食Natalie',description="錯誤:請輸入有效的數量",color=common.bot_error_color))
            return

        # 原子扣除蛋糕並暫加經驗（之後再依等級上限校正）
        userid = str(interaction.user.id)
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        consume_result = await userdata_collection.find_one_and_update(
            {"_id": userid, "cake": {"$gte": eat_cake}},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key not in {"cake", "level_exp"}}, "$inc": {"cake": -eat_cake, "level_exp": eat_cake}},
            upsert=False,
            return_document=common.ReturnDocument.AFTER,
        )
        if consume_result is None:
            await interaction.response.send_message(embed=Embed(title='餵食Natalie',description="你自己都沒蛋糕了還想餵我??",color=common.bot_error_color))
            return

        # 計算距離等級上限還能吸收多少經驗，超過的部分改為退還蛋糕
        userlevel = common.LevelSystem()
        max_level = userlevel.max_level
        max_level_exp = userlevel.max_level_exp()
        previous_exp = consume_result.get("level_exp", 0) - eat_cake
        if previous_exp < 0:
            previous_exp = 0
        exp_room = max(0, max_level_exp - previous_exp)
        actual_gained = min(eat_cake, exp_room)
        refund_cake = eat_cake - actual_gained

        # 套用實際獲得的經驗，準備等級結算
        userlevel.level = consume_result.get("level", 1)
        userlevel.level_exp = previous_exp + actual_gained
        userlevel.level_next_exp = consume_result.get(
            "level_next_exp",
            userlevel.next_exp_for_level(userlevel.level),
        )

        # 依經驗值升級，最高到等級上限為止
        leveled_up = False
        while (
            userlevel.level < max_level
            and userlevel.level_exp >= userlevel.level_next_exp
        ):
            userlevel.level += 1
            userlevel.level_next_exp = userlevel.next_exp_for_level(userlevel.level)
            leveled_up = True

        # 到達上限時鎖定等級與經驗，避免再往上衝
        if userlevel.level >= max_level:
            userlevel.level = max_level
            userlevel.level_exp = min(userlevel.level_exp, max_level_exp)
            userlevel.level_next_exp = max_level_exp

        # 寫回等級／經驗；若有超額蛋糕則一併退還
        update_ops = {}
        set_fields = {
            "level": userlevel.level,
            "level_exp": userlevel.level_exp,
            "level_next_exp": userlevel.level_next_exp,
        }
        if (
            leveled_up
            or refund_cake > 0
            or consume_result.get("level_exp") != userlevel.level_exp
            or consume_result.get("level") != userlevel.level
            or consume_result.get("level_next_exp") != userlevel.level_next_exp
        ):
            update_ops["$set"] = set_fields
        if refund_cake > 0:
            update_ops["$inc"] = {"cake": refund_cake}
        if update_ops:
            await userdata_collection.update_one({"_id": userid}, update_ops)

        # 回覆餵食結果（已滿等／升級／部分退還）
        if actual_gained == 0:
            message = Embed(
                title='餵食Natalie',
                description="我已經滿足了!剩下的蛋糕你拿去自己吃掉吧<:frog_cute:1408403070441754765>",
                color=common.bot_color,
            )
        else:
            message = Embed(
                title='餵食Natalie',
                description=f"我吃飽啦!(獲得**{actual_gained}**點經驗值)",
                color=common.bot_color,
            )
            if leveled_up:
                message.add_field(name="升級!", value=f"你現在{userlevel.level}等了。", inline=False)
            if refund_cake > 0:
                message.add_field(
                    name="退還蛋糕",
                    value=f"已達等級上限（**{max_level}**等），多餘的**{refund_cake}**塊{common.cake_emoji}已退還。",
                    inline=False,
                )

        await interaction.response.send_message(embed=message)

    @app_commands.command(name = "level_leaderboard", description = "等級排行榜")
    async def level_leaderboard(self,interaction):
        userid = str(interaction.user.id)
        userdata_collection = common.mongo_storage.get_collection("userdata")
        sorted_data = []
        async for document in userdata_collection.find({"_id": {"$ne": "global"}, "level_exp": {"$exists": True}}).sort("level_exp", -1):
            sorted_data.append((str(document.get("_id")), document))
        # 建立排名榜的列表，以經驗值為排序準則，並倒序排列
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

        message = "\n".join(lines) if lines else "目前還沒有可顯示的等級資料。"

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
        userdata_collection = common.mongo_storage.get_collection("userdata")
        sorted_data = []
        async for document in userdata_collection.find({"_id": {"$ne": "global"}, "voice_active_minutes": {"$gt": 10}}).sort("voice_active_minutes", -1).limit(10):
            sorted_data.append((str(document.get("_id")), document))

        message = Embed(title="語音活躍排行榜",description="",color=common.bot_color)
        leaderboard_message = "注意:需要在語音內至少10分鐘才會記錄至排行榜。\n"
        # 顯示排名榜前10名
        for i, (userid, user_data) in enumerate(sorted_data):
            user = self.bot.get_user(int(userid))
            username = user.display_name if user else f"User({userid})"
            leaderboard_message += f"{i+1}.{username} 語音分鐘數:**{user_data['voice_active_minutes']}**\n"
        message.description = leaderboard_message

        # 昨日排行榜
        global_document = await userdata_collection.find_one({"_id": "global"}, {"yesterday_voice_leaderboard": 1})
        yesterday_voice_leaderboard = ""
        if isinstance(global_document, dict):
            yesterday_voice_leaderboard = str(global_document.get("yesterday_voice_leaderboard", ""))
        if yesterday_voice_leaderboard:
            message.add_field(name="昨日前三名",value=yesterday_voice_leaderboard,inline=False)

        await interaction.response.send_message(embed=message)

    @app_commands.command(name="cake_leaderboard", description="蛋糕排行榜")
    async def cake_leaderboard(self, interaction):
        userdata_collection = common.mongo_storage.get_collection("userdata")
        sorted_data = []
        async for document in userdata_collection.find({"_id": {"$ne": "global"}, "cake": {"$gt": 0}}).sort("cake", -1):
            sorted_data.append((str(document.get("_id")), document))

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
        user_data = await common.mongo_storage.get_user(user_id)
        user_cake = int(user_data.get("cake", 0)) if isinstance(user_data, dict) else 0
        self_rank = None
        for idx, (userid, user_data_item) in enumerate(sorted_data):
            if userid == user_id:
                self_rank = idx + 1
                break

        if self_rank:
            embed.add_field(
                name="你的排名",
                value=f"你目前排名: **{self_rank}**  持有{cake_emoji}: **{user_cake}**",
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
        memberid = str(member.id)
        current_data = await common.mongo_storage.ensure_user_document(memberid)
        cake_before = int(current_data.get("cake", 0))
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        new_data = await userdata_collection.find_one_and_update(
            {"_id": memberid},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": amount}},
            upsert=True,
            return_document=common.ReturnDocument.AFTER,
        )
        cake_after = int(new_data.get("cake", cake_before))
        cake_emoji = common.cake_emoji
        await interaction.response.send_message(embed=Embed(title="為用戶增加蛋糕",description=f"<@{member.id}>資料變更...\n原始{cake_emoji}:**{cake_before}**\n增加了**{amount}**塊{cake_emoji}\n現在有**{cake_after}**塊{cake_emoji}",color=common.bot_color))

    async def serveritem_autocomplete(self, interaction: discord.Interaction, current: str):
        """
        伺服器道具名稱選單。

        Args:
            interaction (discord.Interaction): "指令互動"
            current (str): "防"

        Returns:
            choices (list): "[Choice(name='防盜卡(3天)', value='anti_theft_3')]"
        """
        keyword = current.lower()
        choices = []
        for item_id, item in self.server_item_house.items.items():
            name = item["name"]
            if keyword and keyword not in name.lower() and keyword not in item_id.lower():
                continue
            choices.append(app_commands.Choice(name=name, value=item_id))
            if len(choices) >= 25:
                break
        return choices

    @app_commands.command(name="bag", description="查看或使用背包道具")
    @app_commands.describe(index="要使用的欄位編號（1～99），留空則只查看", member="需要指定對象的道具")
    @app_commands.rename(index="編號", member="對象")
    async def bag(self, interaction: discord.Interaction, index: Optional[int] = None, member: Optional[discord.Member] = None):
        """
        查看背包或使用指定格子的道具。

        Args:
            interaction (discord.Interaction): "指令互動"
            index (int | None): "1"
            member (discord.Member | None): "要作用的玩家"
        """
        userid = str(interaction.user.id)
        house = self.server_item_house
        if index is not None:
            ok, description = await house.use_slot(userid, index, member, interaction.user)
            color = common.bot_color if ok else common.bot_error_color
            await interaction.response.send_message(embed=Embed(title="Natalie 背包", description=description, color=color))
            return
        user_data = await house.load_user(userid)
        hidden = house.has_status_in_data(user_data, house.status_camo_bag)
        embed = await house.build_bag_embed(userid, 0)
        await interaction.response.send_message(embed=embed, view=BagPageView(house, interaction.user.id, 0), ephemeral=hidden)

    @app_commands.command(name="serveritem_add", description="給予玩家伺服器道具（僅擁有者）")
    @app_commands.describe(member="要給予的玩家", item="要加入的道具", quantity="數量")
    @app_commands.rename(member="用戶", item="東西", quantity="數量")
    @app_commands.autocomplete(item=serveritem_autocomplete)
    async def serveritem_add(self, interaction: discord.Interaction, member: discord.Member, item: str, quantity: int):
        """
        把伺服器道具放入指定玩家背包。

        Args:
            interaction (discord.Interaction): "指令互動"
            member (discord.Member): "要給予的玩家"
            item (str): "anti_theft_3"
            quantity (int): "1"
        """
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="給予伺服器道具", description="權限不足。", color=common.bot_error_color))
            return
        house = self.server_item_house
        if item not in house.items:
            await interaction.response.send_message(embed=Embed(title="給予伺服器道具", description="找不到這個道具。", color=common.bot_error_color))
            return
        if quantity <= 0:
            await interaction.response.send_message(embed=Embed(title="給予伺服器道具", description="數量必須為正整數。", color=common.bot_error_color))
            return
        if not await house.add_items(str(member.id), item, quantity):
            await interaction.response.send_message(embed=Embed(title="給予伺服器道具", description=f"<@{member.id}> 的背包已滿，無法放入 **{house.item_display_name(item)}**。", color=common.bot_error_color))
            return
        await interaction.response.send_message(embed=Embed(
            title="給予伺服器道具",
            description=f"已把 **{house.item_display_name(item)} x{quantity}** 放入 <@{member.id}> 的背包。",
            color=common.bot_color,
        ))

    @app_commands.command(name = "giveaway_join", description = "加入抽獎頻道")
    async def giveaway_join(self,interaction):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            userlevel = await common.LevelSystem().read_info(userid)
        if userlevel.level >= 5 and all(role.id not in [621764669929160715, common.vip_role_id] for role in interaction.user.roles):
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
            "587934995063111681", #xu6
            "823967449149603861" #小八
        ]
        if userid not in whitelist:
            await interaction.response.send_message(embed=Embed(title="權限不足",description="你無法使用這個指令!\n此指令僅供白名單使用。",color=common.bot_error_color), ephemeral=True)
            return

        if timeset < 15 or timeset > 60:
            await interaction.response.send_message(embed=Embed(title="設置失敗",description="時間範圍僅能選擇15~60分鐘!",color=common.bot_error_color), ephemeral=True)
            return

        await common.mongo_storage.update_user_fields(userid, {"afkdisconnect_trigger": timeset})

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

    async def remove_all_color_roles(self, member, reason="移除顏色身分組"):
        """
        移除成員身上所有靜態與動態顏色身分組

        Args:
            member: Discord 成員物件
            reason (str): "移除顏色身分組"
        """
        color_role_ids = {attributes["role_id"] for attributes in self.color_dict.values()}
        color_role_ids.update(attributes["role_id"] for attributes in self.animation_color_dict.values())
        for role in member.roles:
            if role.id in color_role_ids:
                await member.remove_roles(role, reason=reason)

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
        app_commands.Choice(name="移除顏色身份組", value="移除顏色身份組"),
        ])
    async def set_color(self, interaction, colorchoice:app_commands.Choice[str]):
        userid = str(interaction.user.id)
        user_roles = interaction.user.roles

        if colorchoice.value == "移除顏色身份組":
            await self.remove_all_color_roles(interaction.user)
            await interaction.response.send_message(embed=Embed(title="移除顏色身分組",description="已移除你身上所有的顏色身分組!",color=common.bot_color))
            return

        async with common.jsonio_lock:
            userlevel = await common.LevelSystem().read_info(userid)

        if any(role.name == colorchoice.value for role in user_roles):
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"你目前的顏色已經是 <@&{self.color_dict[colorchoice.value]['role_id']}> 了!",color=common.bot_error_color))
            return

        #只有靜態身分組才會看等級
        if colorchoice.value in self.color_dict and userlevel.level < self.color_dict[colorchoice.value]['需求等級']:
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"等級不足! <@&{self.color_dict[colorchoice.value]['role_id']}> 需要**{self.color_dict[colorchoice.value]['需求等級']}**等，你目前只有**{userlevel.level}**等。",color=common.bot_error_color))
            return

        await self.remove_all_color_roles(interaction.user, reason="移除舊的顏色身分組")

        if colorchoice.value in self.color_dict:
            await interaction.user.add_roles(interaction.guild.get_role(self.color_dict[colorchoice.value]['role_id']),reason="更換顏色身分組")
            await interaction.response.send_message(embed=Embed(title="設置顏色身分組",description=f"你目前的顏色變更為...<@&{self.color_dict[colorchoice.value]['role_id']}>!",color=common.bot_color))

    async def has_animation_color_access(self, user_id: str, member) -> bool:
        """
        是否可用動態顏色：程式白名單、商店 DB 白名單，或至寶身分組。

        Args:
            user_id (str): "410847926236086272"
            member: Discord 成員

        Returns:
            allowed (bool): "True"
        """
        if str(user_id) in self.animation_color_code_whitelist:
            return True
        if any(role.id == common.super_vip_id for role in member.roles):
            return True
        shop_house = getattr(self.bot, "shop_house", None)
        if shop_house is None:
            return False
        return await shop_house.has_animation_color_grant(user_id)

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
        app_commands.Choice(name="移除顏色身份組", value="移除顏色身份組"),
        ])
    async def set_animation_color(self, interaction, colorchoice:app_commands.Choice[str]):
        userid = str(interaction.user.id)

        user_roles = interaction.user.roles

        if colorchoice.value == "移除顏色身份組":
            await self.remove_all_color_roles(interaction.user)
            await interaction.response.send_message(embed=Embed(title="移除顏色身分組",description="已移除你身上所有的顏色身分組!",color=common.bot_color))
            return

        if any(role.name == colorchoice.value for role in user_roles):
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"你目前的顏色已經是 <@&{self.animation_color_dict[colorchoice.value]['role_id']}> 了!",color=common.bot_error_color))
            return

        if colorchoice.value in self.animation_color_dict and not await self.has_animation_color_access(userid, interaction.user):
            await interaction.response.send_message(embed=Embed(title="錯誤",description=f"你當前無法使用 <@&{self.animation_color_dict[colorchoice.value]['role_id']}> !\n動態身分組使用權可以在商店獲得!",color=common.bot_error_color))
            return

        await self.remove_all_color_roles(interaction.user, reason="移除舊的顏色身分組")

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
        if session.short_message:
            embed.add_field(name="短言", value=session.short_message, inline=False)
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
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="你剛剛不是才拿過嗎，手別伸第二次。", color=common.bot_error_color), ephemeral=True)
                return
            if not session.remaining_amounts:
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="晚了一步，紅包已經空了。", color=common.bot_error_color), ephemeral=True)
                return
            amount = session.remaining_amounts.popleft()
            display_name = interaction.user.display_name
            session.claimed_user_ids.add(uid)
            session.claimed_order.append((uid, display_name, amount))
            done_all = len(session.remaining_amounts) == 0
        rid = str(uid)
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        await userdata_collection.update_one({"_id": rid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": amount}}, upsert=True)
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
        oid = str(session.creator_id)
        if refund > 0:
            userdata_collection = common.mongo_storage.get_collection("userdata")
            defaults = common.mongo_storage.get_user_defaults()
            await userdata_collection.update_one({"_id": oid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": refund}}, upsert=True)
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
        people_field = discord.ui.TextInput(label="人數 (3～15)", placeholder="要發給幾個人", required=True, max_length=2)
        total_field = discord.ui.TextInput(label="總金額 (蛋糕)", placeholder="整數，未搶完會退回剩餘", required=True, max_length=12)
        short_message_field = discord.ui.TextInput(label="短言", placeholder="可留空，最多 100 字", required=False, max_length=100)

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
            short_message_raw = self.short_message_field.value or ""
            short_message = short_message_raw.strip()
            try:
                amounts = self.parent_cog.compute_red_packet_amounts(total, people)
            except ValueError as error:
                await interaction.response.send_message(embed=Embed(title="搶紅包", description=str(error), color=common.bot_error_color), ephemeral=True)
                return
            creator_id = interaction.user.id
            oid = str(creator_id)
            userdata_collection = common.mongo_storage.get_collection("userdata")
            defaults = common.mongo_storage.get_user_defaults()
            spend_result = await userdata_collection.find_one_and_update(
                {"_id": oid, "cake": {"$gte": total}},
                {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": -total}},
                upsert=False,
                return_document=common.ReturnDocument.AFTER,
            )
            if spend_result is None:
                user_data = await common.mongo_storage.ensure_user_document(oid)
                await interaction.response.send_message(
                    embed=Embed(title="搶紅包", description=f"蛋糕不足，你目前有 **{user_data.get('cake', 0)}** 塊{common.cake_emoji}。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            ends_at = datetime.now(timezone.utc) + timedelta(minutes=5)
            session = RedPacketSession(creator_id, total, people, amounts, ends_at, short_message if short_message else None)
            channel = interaction.guild.get_channel(self.channel_id)
            if channel is None or not isinstance(channel, discord.TextChannel):
                await userdata_collection.update_one({"_id": oid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": total}}, upsert=True)
                await interaction.response.send_message(embed=Embed(title="搶紅包", description="找不到指定的文字頻道，已退回蛋糕。", color=common.bot_error_color), ephemeral=True)
                return
            view = RedPacketGrabView(self.parent_cog, session)
            embed = self.parent_cog.build_red_packet_embed(session)
            await interaction.response.defer(ephemeral=True)
            try:
                msg = await channel.send(embed=embed, view=view)
            except discord.HTTPException:
                await userdata_collection.update_one({"_id": oid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": total}}, upsert=True)
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

    def member_has_super_vip(self, member: discord.Member) -> bool:
        """
        判斷成員是否擁有至寶身分組。

        Args:
            member (discord.Member): "伺服器成員"

        Returns:
            result (bool): "True"
        """
        return any(role.id == common.super_vip_id for role in member.roles)

    async def is_voice_trace_hidden(self, member: discord.Member) -> bool:
        """
        判斷至寶是否已開啟隱藏語音足跡。

        Args:
            member (discord.Member): "伺服器成員"

        Returns:
            result (bool): "True"
        """
        if not self.member_has_super_vip(member): return False
        user_data = await common.mongo_storage.get_user(str(member.id))
        if not isinstance(user_data, dict): return False
        return bool(user_data.get("hide_voice_trace"))

    async def revoke_super_vip_voice_privileges(self, member: discord.Member) -> None:
        """
        失去至寶時撤銷語音日誌瀏覽權與隱藏足跡設定。

        Args:
            member (discord.Member): "剛失去至寶的成員"
        """
        channel = self.bot.get_channel(common.mod_log_channel)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.set_permissions(member, overwrite=None)
            except discord.HTTPException:
                pass
        await common.mongo_storage.unset_user_fields(str(member.id), ["hide_voice_trace"])

    def build_svip_info_embed(self) -> Embed:
        """
        建立至寶介紹與特權說明的 embed。

        Returns:
            embed (Embed): "至寶特權說明"
        """
        privilege_text = "\n".join(f"- {line}" for line in self.svip_privilege_lines)
        embed = Embed(title="至寶介紹", description=self.svip_intro, color=common.bot_color)
        embed.add_field(name="至寶特權", value=privilege_text, inline=False)
        return embed

    async def send_super_vip_welcome_dm(self, member: discord.Member) -> None:
        """
        恭喜新至寶並提示可使用 /svip_info 查看特權。

        Args:
            member (discord.Member): "剛獲得至寶的成員"
        """
        embed = Embed(
            title="恭喜成為至寶！",
            description="恭喜你成為今日的至寶！\n可以使用 `/svip_info` 查看你擁有的特權。",
            color=common.bot_color,
        )
        try:
            await member.send(embed=embed)
        except discord.HTTPException:
            pass

    def can_use_svip_info(self, user: discord.abc.User) -> bool:
        """
        判斷是否為至寶或 bot owner，可使用 svip_info。

        Args:
            user (discord.abc.User): "指令使用者"

        Returns:
            result (bool): "True"
        """
        if user.id == common.bot_owner_id: return True
        if isinstance(user, discord.Member): return self.member_has_super_vip(user)
        return False

    @app_commands.command(name="svip_info", description="至寶特權：查看至寶介紹與特權說明")
    async def svip_info(self, interaction: discord.Interaction) -> None:
        """
        以只有自己看得到的方式顯示至寶介紹與特權。

        Args:
            interaction (discord.Interaction): "斜線指令互動"
        """
        if interaction.guild is None or interaction.guild.id != common.fake_sister_server_id:
            await interaction.response.send_message(embed=Embed(title="至寶介紹", description="此指令僅能在「偽造妹妹」伺服器使用。", color=common.bot_error_color), ephemeral=True)
            return
        if not self.can_use_svip_info(interaction.user):
            await interaction.response.send_message(embed=Embed(title="權限不足", description="此指令僅供至寶使用。", color=common.bot_error_color), ephemeral=True)
            return
        await interaction.response.send_message(embed=self.build_svip_info_embed(), ephemeral=True)

    @app_commands.command(name="show_voice_log", description="至寶特權：選擇是否查看語音頻道日誌")
    @app_commands.describe(choice="是否查看語音頻道日誌")
    @app_commands.rename(choice="開關")
    @app_commands.choices(choice=[
        app_commands.Choice(name="開啟", value="開啟"),
        app_commands.Choice(name="關閉", value="關閉"),
    ])
    async def show_voice_log(self, interaction: discord.Interaction, choice: app_commands.Choice[str]) -> None:
        """
        為至寶開關管理員日誌頻道的瀏覽權限。

        Args:
            interaction (discord.Interaction): "斜線指令互動"
            choice (app_commands.Choice[str]): "開啟"
        """
        if interaction.guild is None or interaction.guild.id != common.fake_sister_server_id:
            await interaction.response.send_message(embed=Embed(title="語音頻道日誌", description="此指令僅能在「偽造妹妹」伺服器使用。", color=common.bot_error_color), ephemeral=True)
            return
        if not self.member_has_super_vip(interaction.user):
            await interaction.response.send_message(embed=Embed(title="權限不足", description="此指令僅供至寶使用。", color=common.bot_error_color), ephemeral=True)
            return

        channel = self.bot.get_channel(common.mod_log_channel)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(embed=Embed(title="語音頻道日誌", description="找不到語音日誌頻道。", color=common.bot_error_color), ephemeral=True)
            return

        try:
            if choice.value == "開啟":
                await channel.set_permissions(interaction.user, view_channel=True, read_message_history=True)
                await interaction.response.send_message(embed=Embed(title="語音頻道日誌", description=f"已開啟，你現在可以查看 {channel.mention}。", color=common.bot_color), ephemeral=True)
                return
            await channel.set_permissions(interaction.user, overwrite=None)
            await interaction.response.send_message(embed=Embed(title="語音頻道日誌", description="已關閉語音頻道日誌瀏覽權限。", color=common.bot_color), ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message(embed=Embed(title="語音頻道日誌", description="無法變更頻道權限，請稍後再試或聯繫管理員。", color=common.bot_error_color), ephemeral=True)

    @app_commands.command(name="hide_voice_trace", description="至寶特權：選擇是否隱藏自己的語音頻道足跡")
    @app_commands.describe(choice="是否隱藏語音進出日誌")
    @app_commands.rename(choice="開關")
    @app_commands.choices(choice=[
        app_commands.Choice(name="開啟", value="開啟"),
        app_commands.Choice(name="關閉", value="關閉"),
    ])
    async def hide_voice_trace(self, interaction: discord.Interaction, choice: app_commands.Choice[str]) -> None:
        """
        為至寶開關隱藏語音進出／切換日誌。

        Args:
            interaction (discord.Interaction): "斜線指令互動"
            choice (app_commands.Choice[str]): "開啟"
        """
        if interaction.guild is None or interaction.guild.id != common.fake_sister_server_id:
            await interaction.response.send_message(embed=Embed(title="隱藏語音足跡", description="此指令僅能在「偽造妹妹」伺服器使用。", color=common.bot_error_color), ephemeral=True)
            return
        if not self.member_has_super_vip(interaction.user):
            await interaction.response.send_message(embed=Embed(title="權限不足", description="此指令僅供至寶使用。", color=common.bot_error_color), ephemeral=True)
            return

        userid = str(interaction.user.id)
        if choice.value == "開啟":
            await common.mongo_storage.update_user_fields(userid, {"hide_voice_trace": True})
            await interaction.response.send_message(embed=Embed(title="隱藏語音足跡", description="已開啟。你進入、退出、切換語音頻道時不會留下日誌。", color=common.bot_color), ephemeral=True)
            return
        await common.mongo_storage.unset_user_fields(userid, ["hide_voice_trace"])
        await interaction.response.send_message(embed=Embed(title="隱藏語音足跡", description="已關閉。你的語音進出將恢復記錄。", color=common.bot_color), ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self,member, before, after):
        if member.guild.id != 419108485435883531: return #如果語音事件不在妹妹群內則略過(例如在測試群進語音之類的)
        hide_trace = await self.is_voice_trace_hidden(member)
        #進入語音頻道
        if after.channel and not before.channel:
            self.member_invoice_time[str(member.id)] = time.time()
            if not hide_trace:
                embed = Embed(title="", description=f"{member.display_name} 進入了 {after.channel.name} 語音頻道", color=common.bot_color)
                embed.set_author(name=f"{member.global_name}", icon_url=member.avatar)
                embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
                await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

        #離開語音頻道
        if before.channel and not after.channel:
            if not hide_trace:
                embed = Embed(title="", description=f"{member.display_name} 離開了 {before.channel.name} 語音頻道", color=common.bot_color)
                invoice_time = time.time() - self.member_invoice_time.get(str(member.id),60)
                if invoice_time  < 10:
                    embed = Embed(title="", description=f"{member.display_name} 離開了 {before.channel.name} 語音頻道 (在{invoice_time:.2f}秒內進出)", color=0xEAC100)
                self.member_invoice_time.pop(str(member.id),None)
                embed.set_author(name=f"{member.global_name}", icon_url=member.avatar)
                embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
                await self.bot.get_channel(common.mod_log_channel).send(embed=embed)
            else:
                self.member_invoice_time.pop(str(member.id), None)

            member_data = await common.mongo_storage.get_user(str(member.id))
            if isinstance(member_data, dict) and "afk_start" in member_data:
                await common.mongo_storage.unset_user_fields(str(member.id), ["afk_start"])

        #切換語音頻道
        if before.channel != after.channel:
            if before.channel and after.channel:
                if not hide_trace:
                    embed = Embed(title="", description=f"{member.display_name} 從 {before.channel.name} 移動到 {after.channel.name} 頻道", color=common.bot_color)
                    #如果除了自己外房間還有其他人，則檢查進出時間
                    if len(before.channel.members) >= 2:
                        invoice_time = time.time() - self.member_invoice_time.get(str(member.id),60)
                        if invoice_time  < 10:
                            embed = Embed(title="", description=f"{member.display_name} 從 {before.channel.name} 移動到 {after.channel.name} 頻道 (在{invoice_time:.2f}秒內切換頻道)", color=0xEAC100)
                    embed.set_author(name=f"{member.global_name}", icon_url=member.avatar)
                    embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
                    await self.bot.get_channel(common.mod_log_channel).send(embed=embed)
                self.member_invoice_time[str(member.id)] = time.time()

    def format_message_audit_content(self, content: str | None) -> str:
        """
        整理訊息內容供日誌顯示，過長則截斷。

        Args:
            content (str | None): "訊息原文，可能為空"

        Returns:
            result (str): "(無文字內容) 或截斷後文字"
        """
        if not content:
            return "(無文字內容)"
        if len(content) <= self.message_audit_content_limit:
            return content
        return f"{content[:self.message_audit_content_limit - 3]}..."

    async def collect_message_audit_files(self, message: discord.Message) -> tuple[list[discord.File], list[str]]:
        """
        下載原訊息附件，供刪除日誌重傳到日誌頻道。

        Args:
            message (discord.Message): "被刪除的原訊息"

        Returns:
            result (tuple[list[discord.File], list[str]]): "成功的附件清單, 無法重傳的檔名說明"
        """
        files: list[discord.File] = []
        failed_notes: list[str] = []
        max_size = message.guild.filesize_limit if message.guild else 25 * 1024 * 1024
        attachments = message.attachments[:self.message_audit_max_attachments]
        for skipped in message.attachments[self.message_audit_max_attachments:]:
            failed_notes.append(f"{skipped.filename}（超過單則訊息附件上限）")

        for attachment in attachments:
            if attachment.size > max_size:
                failed_notes.append(f"{attachment.filename}（超過大小限制）")
                continue
            try:
                files.append(await attachment.to_file(spoiler=attachment.is_spoiler()))
            except (discord.HTTPException, discord.NotFound, OSError, asyncio.TimeoutError):
                failed_notes.append(f"{attachment.filename}（下載失敗）")
        return files, failed_notes

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """
        監控訊息編輯，將頻道、作者、編輯前後內容送到管理員日誌。
        """
        if after.guild is None or after.guild.id != common.fake_sister_server_id: return
        if after.author.bot: return
        if before.content == after.content: return

        embed = Embed(title="訊息編輯", color=0xEAC100)
        embed.set_author(name=after.author.display_name, icon_url=after.author.display_avatar.url)
        embed.add_field(name="頻道", value=after.channel.mention, inline=False)
        embed.add_field(name="作者", value=f"{after.author.mention} (`{after.author.id}`)", inline=False)
        embed.add_field(name="編輯前", value=self.format_message_audit_content(before.content), inline=False)
        embed.add_field(name="編輯後", value=self.format_message_audit_content(after.content), inline=False)
        embed.add_field(name="訊息連結", value=after.jump_url, inline=False)
        embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
        await self.bot.get_channel(common.admin_log_channel).send(embed=embed)
        await self.external_invite_detect(after)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """
        監控訊息刪除，將頻道、作者、原訊息內容與附件送到管理員日誌。
        """
        if message.guild is None or message.guild.id != common.fake_sister_server_id: return
        if message.author.bot: return

        embed = Embed(title="訊息刪除", color=common.bot_error_color)
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="頻道", value=message.channel.mention, inline=False)
        embed.add_field(name="作者", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
        embed.add_field(name="內容", value=self.format_message_audit_content(message.content), inline=False)

        files: list[discord.File] = []
        if message.attachments:
            files, failed_notes = await self.collect_message_audit_files(message)
            if files:
                embed.add_field(name="附件", value=f"已重傳 {len(files)} 個檔案", inline=False)
            if failed_notes:
                embed.add_field(name="未重傳的附件", value=self.format_message_audit_content("\n".join(failed_notes)), inline=False)

        embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
        await self.bot.get_channel(common.admin_log_channel).send(embed=embed, files=files)

    @commands.Cog.listener()
    async def on_member_join(self,member):  
        await common.mongo_storage.ensure_user_document(str(member.id))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        成員離開伺服器時，將紀錄送到管理員日誌。
        """
        if member.guild.id != common.fake_sister_server_id: return

        embed = Embed(title="成員離開", description=f"{member.mention} {member.display_name}", color=common.bot_error_color)
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_footer(text=str(member.id))
        embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
        await self.bot.get_channel(common.admin_log_channel).send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self,message):
        if message.author.bot:
            return

        memberid = str(message.author.id)
        now = datetime.now()
        # 如果成員還沒有獲得過蛋糕，或者已經過了冷卻時間
        if memberid not in self.last_cake_time or now - self.last_cake_time[memberid] > self.cake_cooldown:
            userdata_collection = common.mongo_storage.get_collection("userdata")
            defaults = common.mongo_storage.get_user_defaults()
            await userdata_collection.update_one({"_id": memberid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": 1}}, upsert=True)
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
        #外群邀請連結偵測
        await self.external_invite_detect(message)

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

    async def external_invite_detect(self, message: discord.Message) -> None:
        """
        偵測並刪除指向其他伺服器的 Discord 邀請連結訊息。

        Args:
            message (discord.Message): "discord.gg/abc123"
        """
        if message.guild is None or message.guild.id != common.fake_sister_server_id:
            return
        if message.author.bot or not message.content:
            return

        seen_codes: set[str] = set()
        has_external_invite = False
        for code in self.invite_link_pattern.findall(message.content):
            normalized_code = code.lower()
            if normalized_code in seen_codes:
                continue
            seen_codes.add(normalized_code)

            try:
                invite = await self.bot.fetch_invite(code)
            except discord.NotFound:
                continue
            except discord.HTTPException:
                continue

            if invite.guild is None or invite.guild.id != common.fake_sister_server_id:
                has_external_invite = True
                break

        if not has_external_invite:
            return

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            return

        try:
            notice_embed = Embed(
                title="訊息刪除通知",
                description="在「偽造妹妹」，傳送其他群組的邀請連結是不被允許的，如果想要拉其他玩家進入其他群組，請透過私訊發送邀請。",
                color=common.bot_error_color,
            )
            await message.author.send(embed=notice_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

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
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Nitro Booster 進出時同步 VIP；至寶進出時歡迎私訊或撤銷語音日誌特權。
        """
        if after.guild.id == common.fake_sister_server_id:
            had_super_vip = any(role.id == common.super_vip_id for role in before.roles)
            has_super_vip = any(role.id == common.super_vip_id for role in after.roles)
            if had_super_vip and not has_super_vip:
                await self.revoke_super_vip_voice_privileges(after)
            elif not had_super_vip and has_super_vip:
                await self.send_super_vip_welcome_dm(after)

        before_has_booster = any(role.id == common.nitro_booster_role_id for role in before.roles)
        after_has_booster = any(role.id == common.nitro_booster_role_id for role in after.roles)
        if before_has_booster == after_has_booster: return

        vip_role = after.guild.get_role(common.vip_role_id)
        if vip_role is None: return
        retain_delta = timedelta(days=self.vip_retain_days)

        # 新加入的 Booster：尚未有 VIP 則賦予並記錄時間
        if after_has_booster:
            if vip_role in after.roles: return
            await after.add_roles(vip_role, reason="新的Nitro Booster加入，賦予VIP身分組")
            await common.mongo_storage.update_user_fields(str(after.id), {"vip_join_time": datetime.now()})
            return

        # 離開 Booster：未滿保留天數則移除 VIP
        if vip_role not in after.roles: return
        member_data = await common.mongo_storage.get_user(str(after.id))
        # 無紀錄時視為已滿期，不移除 VIP
        vip_join_time = datetime.now() - retain_delta
        if isinstance(member_data, dict):
            vip_join_time = member_data.get("vip_join_time", vip_join_time)
        if datetime.now() - vip_join_time >= retain_delta: return
        await after.remove_roles(vip_role, reason="Nitro Booster身分組未達30天就離開，移除VIP身分組")
        await common.mongo_storage.unset_user_fields(str(after.id), ["vip_join_time"])

async def setup(client:commands.Bot):
    await client.add_cog(General(client))