import asyncio
from datetime import datetime, timezone

import discord
from discord import Embed, app_commands
from discord.ext import commands

from . import common


class ShopLinkView(discord.ui.View):
    """商店指令的前往面板按鈕。"""

    def __init__(self, page_url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="前往商店", style=discord.ButtonStyle.link, url=page_url))


class ShopHouse:
    """商店目錄、掛單、成交與道具轉移。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.category_server = "server"
        self.category_mining = "mining"
        self.category_labels = {
            self.category_server: "伺服器道具",
            self.category_mining: "挖礦遊戲",
        }
        self.kind_mining_collection = "mining_collection"
        self.kind_animation_color = "animation_color_pass"
        self.product_animation_color_id = "server_item:animation_color"
        self.product_animation_color_name = "動態顏色身份組使用權"
        self.grant_animation_color_id = "animation_color"
        self.order_status_open = "open"
        self.order_status_filled = "filled"
        self.order_status_cancelled = "cancelled"
        self.side_buy = "buy"
        self.side_sell = "sell"
        self.trade_kind_listing = "listing_buy"
        self.trade_kind_quick = "quick_sell"
        self.meta_document_id = "meta"
        self.settings_document_id = "settings"
        self.default_fee_percent = 0.0
        self.fee_percent_min = 0.0
        self.fee_percent_max = 100.0
        self.fee_percent_cache = None
        self.history_limit = 80
        self.product_history_limit = 20

    def page_url(self) -> str:
        """
        組出網頁商店網址。

        Returns:
            url (str): "https://fake-sister.ani20168.com/shop"
        """
        panel = getattr(self.bot, "web_panel", None)
        if panel is not None and panel.public_base_url:
            return f"{panel.public_base_url}/shop"
        port = getattr(panel, "port", 8080) if panel is not None else 8080
        return f"http://localhost:{port}/shop"

    def resolve_name(self, user_id: int | str | None) -> str:
        """
        解析顯示名稱。

        Args:
            user_id (int | str | None): "410847926236086272"

        Returns:
            name (str): "ani"
        """
        if user_id is None:
            return ""
        parsed_id = int(user_id)
        guild = self.bot.get_guild(common.fake_sister_server_id)
        member = guild.get_member(parsed_id) if guild is not None else None
        if member is not None:
            return member.display_name
        user = self.bot.get_user(parsed_id)
        if user is not None:
            return user.display_name
        return str(parsed_id)

    def is_bot_owner(self, user_id: int | str) -> bool:
        """
        是否為總管理員。

        Args:
            user_id (int | str): "410847926236086272"

        Returns:
            is_owner (bool): "True"
        """
        return int(user_id) == common.bot_owner_id

    def now_iso(self) -> str:
        """
        目前 UTC 時間。

        Returns:
            timestamp (str): "2026-08-31T07:00:00+00:00"
        """
        return datetime.now(timezone.utc).isoformat()

    def format_fee_percent(self, percent: float) -> str:
        """
        手續費百分比顯示文字。

        Args:
            percent (float): "5.0"

        Returns:
            text (str): "5"
        """
        text = f"{float(percent):.1f}".rstrip("0").rstrip(".")
        return text or "0"

    def parse_fee_percent(self, value) -> float:
        """
        解析後台填的手續費百分比。

        Args:
            value: "5"

        Returns:
            percent (float): "5.0"
        """
        percent = round(float(value), 1)
        if percent < self.fee_percent_min or percent > self.fee_percent_max:
            raise ValueError("手續費超出範圍")
        return percent

    def fee_amount(self, total: int, fee_percent: float) -> int:
        """
        依成交總額計算手續費蛋糕。

        Args:
            total (int): "1000"
            fee_percent (float): "5.0"

        Returns:
            fee (int): "50"
        """
        if total <= 0 or fee_percent <= 0:
            return 0
        fee = int(total * fee_percent / 100)
        if fee < 0:
            return 0
        if fee > total:
            return total
        return fee

    async def get_fee_percent(self) -> float:
        """
        讀取目前商店手續費百分比。

        Returns:
            percent (float): "5.0"
        """
        if self.fee_percent_cache is not None:
            return self.fee_percent_cache
        collection = common.mongo_storage.get_collection("shop_settings")
        document = await collection.find_one({"_id": self.settings_document_id})
        percent = self.default_fee_percent
        if document is not None:
            try:
                percent = float(document.get("fee_percent", self.default_fee_percent))
            except (TypeError, ValueError):
                percent = self.default_fee_percent
        percent = max(self.fee_percent_min, min(self.fee_percent_max, percent))
        self.fee_percent_cache = percent
        return percent

    async def set_fee_percent(self, value) -> dict:
        """
        儲存商店手續費百分比。

        Args:
            value: "5"

        Returns:
            result (dict): "{'ok': True, 'fee_percent': 5.0}"
        """
        try:
            percent = self.parse_fee_percent(value)
        except (TypeError, ValueError):
            min_text = self.format_fee_percent(self.fee_percent_min)
            max_text = self.format_fee_percent(self.fee_percent_max)
            return {"ok": False, "error": f"手續費必須是 {min_text}～{max_text} 之間的數字"}
        collection = common.mongo_storage.get_collection("shop_settings")
        await collection.replace_one(
            {"_id": self.settings_document_id},
            {"_id": self.settings_document_id, "fee_percent": percent},
            upsert=True,
        )
        self.fee_percent_cache = percent
        return {"ok": True, "fee_percent": percent, "fee_percent_text": self.format_fee_percent(percent)}

    async def settle_trade_cake(self, seller_id: str, total: int) -> tuple[int, int, float]:
        """
        成交後把蛋糕給賣家，並依手續費抽成給機器人。

        Args:
            seller_id (str): "4108"
            total (int): "1000"

        Returns:
            result (tuple): "(950, 50, 5.0)"
        """
        fee_percent = await self.get_fee_percent()
        fee = self.fee_amount(total, fee_percent)
        seller_gain = total - fee
        if seller_gain > 0:
            await self.add_cake(seller_id, seller_gain)
        if fee > 0:
            await self.add_cake(str(common.bot_id), fee)
        return seller_gain, fee, fee_percent

    async def ensure_indexes(self):
        """建立商店查詢用索引。"""
        order_collection = common.mongo_storage.get_collection("shop_order")
        history_collection = common.mongo_storage.get_collection("shop_history")
        await order_collection.create_index([("status", 1), ("product_id", 1), ("side", 1)])
        await order_collection.create_index([("status", 1), ("user_id", 1), ("product_id", 1)])
        await history_collection.create_index([("created_at", -1)])
        await history_collection.create_index([("buyer_id", 1), ("created_at", -1)])
        await history_collection.create_index([("seller_id", 1), ("created_at", -1)])
        await history_collection.create_index([("product_id", 1), ("created_at", -1)])

    def build_mining_product(self, collection_name: str, sort_order: int) -> dict:
        """
        組出挖礦收藏品商品文件。

        Args:
            collection_name (str): "昆蟲化石"
            sort_order (int): "1"

        Returns:
            product (dict): "{'product_id': 'mining_collection:昆蟲化石'}"
        """
        product_id = f"{self.kind_mining_collection}:{collection_name}"
        return {
            "_id": product_id,
            "product_id": product_id,
            "category": self.category_mining,
            "name": collection_name,
            "description": "",
            "kind": self.kind_mining_collection,
            "payload": {"collection_name": collection_name},
            "sort_order": sort_order,
            "flags": {
                "sell_owner_only": False,
                "unlimited_stock": False,
            },
        }

    def build_animation_color_product(self) -> dict:
        """
        組出動態顏色使用權商品文件。

        Returns:
            product (dict): "{'product_id': 'server_item:animation_color'}"
        """
        return {
            "_id": self.product_animation_color_id,
            "product_id": self.product_animation_color_id,
            "category": self.category_server,
            "name": self.product_animation_color_name,
            "description": "",
            "kind": self.kind_animation_color,
            "payload": {},
            "sort_order": 0,
            "flags": {
                "sell_owner_only": True,
                "unlimited_stock": True,
            },
        }

    async def ensure_catalog(self):
        """補齊初版商品，既有描述不覆蓋。"""
        collection = common.mongo_storage.get_collection("shop_product")
        seeds = [self.build_animation_color_product()]
        mining_cog = self.bot.get_cog("MiningGame")
        if mining_cog is not None:
            sort_order = 1
            for item_list in mining_cog.collection_list.values():
                for collection_name in item_list:
                    seeds.append(self.build_mining_product(collection_name, sort_order))
                    sort_order += 1
        for product in seeds:
            await collection.update_one(
                {"_id": product["_id"]},
                {"$setOnInsert": product},
                upsert=True,
            )

    async def allocate_id(self, dataset: str, field_name: str) -> int:
        """
        取得下一個單調遞增 ID。

        Args:
            dataset (str): "shop_order"
            field_name (str): "next_order_id"

        Returns:
            next_id (int): "1"
        """
        collection = common.mongo_storage.get_collection(dataset)
        document = await collection.find_one_and_update(
            {"_id": self.meta_document_id},
            {"$inc": {field_name: 1}},
            upsert=True,
            return_document=common.ReturnDocument.AFTER,
        )
        return int(document[field_name])

    async def get_product(self, product_id: str) -> dict | None:
        """
        讀取商品。

        Args:
            product_id (str): "mining_collection:昆蟲化石"

        Returns:
            product (dict | None): "{'name': '昆蟲化石'}"
        """
        collection = common.mongo_storage.get_collection("shop_product")
        return await collection.find_one({"_id": product_id})

    def can_create_sell(self, user_id: str, product: dict) -> bool:
        """
        這個使用者能不能上架此商品。

        Args:
            user_id (str): "410847926236086272"
            product (dict): "{'flags': {'sell_owner_only': True}}"

        Returns:
            allowed (bool): "False"
        """
        flags = product.get("flags") if isinstance(product.get("flags"), dict) else {}
        if flags.get("sell_owner_only"):
            return self.is_bot_owner(user_id)
        return True

    def collection_name_of(self, product: dict) -> str:
        """
        取出收藏品名稱。

        Args:
            product (dict): "{'payload': {'collection_name': '昆蟲化石'}}"

        Returns:
            collection_name (str): "昆蟲化石"
        """
        payload = product.get("payload") if isinstance(product.get("payload"), dict) else {}
        return str(payload.get("collection_name") or product.get("name") or "")

    async def ensure_mining_user(self, user_id: str):
        """
        確保挖礦使用者文件存在。

        Args:
            user_id (str): "410847926236086272"
        """
        mining_cog = self.bot.get_cog("MiningGame")
        if mining_cog is None:
            raise ValueError("挖礦系統尚未就緒")
        await mining_cog.miningdata_read(str(user_id))

    async def get_collection_count(self, user_id: str, collection_name: str) -> int:
        """
        讀取收藏品數量。

        Args:
            user_id (str): "410847926236086272"
            collection_name (str): "昆蟲化石"

        Returns:
            count (int): "2"
        """
        user_data = await common.mongo_storage.get_user(str(user_id), "mining")
        if not isinstance(user_data, dict):
            return 0
        collections = user_data.get("collections")
        if not isinstance(collections, dict):
            return 0
        return int(collections.get(collection_name) or 0)

    async def change_collection(self, user_id: str, collection_name: str, delta: int) -> bool:
        """
        增減收藏品。扣減時不足會失敗。

        Args:
            user_id (str): "410847926236086272"
            collection_name (str): "昆蟲化石"
            delta (int): "-1"

        Returns:
            ok (bool): "True"
        """
        if delta == 0:
            return True
        await self.ensure_mining_user(user_id)
        mining_collection = common.mongo_storage.get_collection("mining")
        field_name = f"collections.{collection_name}"
        if delta < 0:
            result = await mining_collection.find_one_and_update(
                {"_id": str(user_id), field_name: {"$gte": -delta}},
                {"$inc": {field_name: delta}},
                upsert=False,
                return_document=common.ReturnDocument.AFTER,
            )
            return result is not None
        await mining_collection.update_one({"_id": str(user_id)}, {"$inc": {field_name: delta}}, upsert=True)
        return True

    async def animation_color_grants(self) -> list[str]:
        """
        讀取動態顏色 DB 白名單。

        Returns:
            user_ids (list): "['410847926236086272']"
        """
        collection = common.mongo_storage.get_collection("shop_grant")
        document = await collection.find_one({"_id": self.grant_animation_color_id})
        if not isinstance(document, dict):
            return []
        user_ids = document.get("user_ids")
        if not isinstance(user_ids, list):
            return []
        return [str(user_id) for user_id in user_ids]

    async def has_animation_color_grant(self, user_id: str) -> bool:
        """
        是否已寫入動態顏色 DB 白名單。

        Args:
            user_id (str): "410847926236086272"

        Returns:
            granted (bool): "True"
        """
        collection = common.mongo_storage.get_collection("shop_grant")
        document = await collection.find_one({"_id": self.grant_animation_color_id, "user_ids": str(user_id)})
        return document is not None

    def has_legacy_animation_color(self, user_id: str) -> bool:
        """
        是否在程式寫死的動態顏色白名單。

        Args:
            user_id (str): "410847926236086272"

        Returns:
            granted (bool): "True"
        """
        general_cog = self.bot.get_cog("General")
        if general_cog is None:
            return False
        return str(user_id) in general_cog.animation_color_code_whitelist

    async def already_owns_animation_color(self, user_id: str) -> bool:
        """
        是否已有永久動態顏色使用權（code 或 DB）。

        Args:
            user_id (str): "410847926236086272"

        Returns:
            owned (bool): "True"
        """
        if self.has_legacy_animation_color(user_id):
            return True
        return await self.has_animation_color_grant(user_id)

    async def grant_animation_color(self, user_id: str):
        """
        把會員寫入動態顏色 DB 白名單。

        Args:
            user_id (str): "410847926236086272"
        """
        collection = common.mongo_storage.get_collection("shop_grant")
        await collection.update_one(
            {"_id": self.grant_animation_color_id},
            {"$addToSet": {"user_ids": str(user_id)}},
            upsert=True,
        )

    async def get_owned_count(self, user_id: str, product: dict) -> int | None:
        """
        可販賣庫存。無限庫存回傳 None。

        Args:
            user_id (str): "410847926236086272"
            product (dict): "{'kind': 'mining_collection'}"

        Returns:
            count (int | None): "3"
        """
        flags = product.get("flags") if isinstance(product.get("flags"), dict) else {}
        if flags.get("unlimited_stock"):
            return None
        if product.get("kind") == self.kind_mining_collection:
            return await self.get_collection_count(user_id, self.collection_name_of(product))
        return 0

    async def reserve_item(self, user_id: str, product: dict, quantity: int) -> bool:
        """
        上架時預扣道具。

        Args:
            user_id (str): "410847926236086272"
            product (dict): "{'kind': 'mining_collection'}"
            quantity (int): "2"

        Returns:
            ok (bool): "True"
        """
        flags = product.get("flags") if isinstance(product.get("flags"), dict) else {}
        if flags.get("unlimited_stock"):
            return True
        if product.get("kind") == self.kind_mining_collection:
            return await self.change_collection(user_id, self.collection_name_of(product), -quantity)
        return False

    async def release_item(self, user_id: str, product: dict, quantity: int) -> bool:
        """
        下架時歸還道具。

        Args:
            user_id (str): "410847926236086272"
            product (dict): "{'kind': 'mining_collection'}"
            quantity (int): "2"

        Returns:
            ok (bool): "True"
        """
        flags = product.get("flags") if isinstance(product.get("flags"), dict) else {}
        if flags.get("unlimited_stock"):
            return True
        if product.get("kind") == self.kind_mining_collection:
            return await self.change_collection(user_id, self.collection_name_of(product), quantity)
        return False

    async def deliver_item(self, user_id: str, product: dict, quantity: int) -> bool:
        """
        成交後把道具給買家。之後有技能道具時在這裡加 kind。

        Args:
            user_id (str): "410847926236086272"
            product (dict): "{'kind': 'animation_color_pass'}"
            quantity (int): "1"

        Returns:
            ok (bool): "True"
        """
        if product.get("kind") == self.kind_mining_collection:
            return await self.change_collection(user_id, self.collection_name_of(product), quantity)
        if product.get("kind") == self.kind_animation_color:
            await self.grant_animation_color(user_id)
            return True
        return False

    async def spend_cake(self, user_id: str, amount: int) -> bool:
        """
        原子扣除蛋糕。

        Args:
            user_id (str): "410847926236086272"
            amount (int): "5000"

        Returns:
            ok (bool): "True"
        """
        if amount <= 0:
            return True
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        result = await userdata_collection.find_one_and_update(
            {"_id": str(user_id), "cake": {"$gte": amount}},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": -amount}},
            upsert=False,
            return_document=common.ReturnDocument.AFTER,
        )
        return result is not None

    async def add_cake(self, user_id: str, amount: int):
        """
        增加蛋糕。

        Args:
            user_id (str): "410847926236086272"
            amount (int): "5000"
        """
        if amount <= 0:
            return
        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        await userdata_collection.update_one(
            {"_id": str(user_id)},
            {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": amount}},
            upsert=True,
        )

    async def get_cake(self, user_id: str) -> int:
        """
        讀取蛋糕餘額。

        Args:
            user_id (str): "410847926236086272"

        Returns:
            cake (int): "12000"
        """
        user_data = await common.mongo_storage.ensure_user_document(str(user_id))
        return int(user_data.get("cake", 0) or 0)

    async def list_open_orders(self, product_id: str, side: str) -> list[dict]:
        """
        列出商品的未成交掛單。

        Args:
            product_id (str): "mining_collection:昆蟲化石"
            side (str): "buy"

        Returns:
            orders (list): "[{'order_id': 1}]"
        """
        collection = common.mongo_storage.get_collection("shop_order")
        sort_direction = -1 if side == self.side_buy else 1
        cursor = collection.find(
            {"status": self.order_status_open, "product_id": product_id, "side": side}
        ).sort([("price", sort_direction), ("created_at", 1)])
        return [document async for document in cursor if document.get("_id") != self.meta_document_id]

    def order_to_public(self, order: dict, viewer_id: str) -> dict:
        """
        轉成網頁用的掛單資料。

        Args:
            order (dict): "{'order_id': 1, 'price': 5000}"
            viewer_id (str): "410847926236086272"

        Returns:
            payload (dict): "{'order_id': 1, 'is_mine': False}"
        """
        user_id = str(order.get("user_id") or "")
        return {
            "order_id": int(order.get("order_id") or 0),
            "user_id": user_id,
            "user_name": order.get("user_name") or self.resolve_name(user_id),
            "price": int(order.get("price") or 0),
            "quantity": int(order.get("quantity") or 0),
            "is_mine": user_id == str(viewer_id),
        }

    async def market_stats(self, product_id: str) -> dict:
        """
        統計未成交買賣價。

        Args:
            product_id (str): "mining_collection:昆蟲化石"

        Returns:
            stats (dict): "{'buy_count': 1, 'highest_buy_price': 100}"
        """
        buy_orders = await self.list_open_orders(product_id, self.side_buy)
        sell_orders = await self.list_open_orders(product_id, self.side_sell)
        return {
            "buy_count": len(buy_orders),
            "sell_count": len(sell_orders),
            "highest_buy_price": max((int(order["price"]) for order in buy_orders), default=None),
            "lowest_sell_price": min((int(order["price"]) for order in sell_orders), default=None),
        }

    async def list_categories(self) -> list[dict]:
        """
        商店分類。

        Returns:
            categories (list): "[{'key': 'server', 'label': '伺服器道具'}]"
        """
        return [{"key": key, "label": label} for key, label in self.category_labels.items()]

    async def list_products(self, category: str) -> list[dict]:
        """
        列出分類商品與市況摘要。

        Args:
            category (str): "mining"

        Returns:
            products (list): "[{'product_id': 'mining_collection:昆蟲化石'}]"
        """
        if category not in self.category_labels:
            return []
        product_collection = common.mongo_storage.get_collection("shop_product")
        products = [document async for document in product_collection.find({"category": category}).sort("sort_order", 1)]
        product_ids = [document["product_id"] for document in products]
        stats_map: dict[str, dict] = {
            product_id: {"buy_count": 0, "sell_count": 0, "highest_buy_price": None, "lowest_sell_price": None}
            for product_id in product_ids
        }
        if product_ids:
            order_collection = common.mongo_storage.get_collection("shop_order")
            cursor = order_collection.find(
                {"status": self.order_status_open, "product_id": {"$in": product_ids}}
            )
            async for order in cursor:
                product_id = order.get("product_id")
                stats = stats_map.get(product_id)
                if stats is None:
                    continue
                price = int(order.get("price") or 0)
                if order.get("side") == self.side_buy:
                    stats["buy_count"] += 1
                    if stats["highest_buy_price"] is None or price > stats["highest_buy_price"]:
                        stats["highest_buy_price"] = price
                elif order.get("side") == self.side_sell:
                    stats["sell_count"] += 1
                    if stats["lowest_sell_price"] is None or price < stats["lowest_sell_price"]:
                        stats["lowest_sell_price"] = price
        result = []
        for product in products:
            stats = stats_map.get(product["product_id"], {})
            result.append(
                {
                    "product_id": product["product_id"],
                    "name": product.get("name") or product["product_id"],
                    "kind": product.get("kind"),
                    "buy_count": stats.get("buy_count", 0),
                    "sell_count": stats.get("sell_count", 0),
                    "highest_buy_price": stats.get("highest_buy_price"),
                    "lowest_sell_price": stats.get("lowest_sell_price"),
                    "description": str(product.get("description") or ""),
                }
            )
        return result

    def owned_label(self, owned: int | None) -> str:
        """
        庫存顯示文字。

        Args:
            owned (int | None): "None"

        Returns:
            label (str): "無限"
        """
        return "無限" if owned is None else str(owned)

    async def list_product_history(self, product_id: str) -> list[dict]:
        """
        此商品最近成交。

        Args:
            product_id (str): "mining_collection:昆蟲化石"

        Returns:
            items (list): "[{'price': 5000}]"
        """
        collection = common.mongo_storage.get_collection("shop_history")
        cursor = collection.find({"product_id": product_id}).sort("created_at", -1).limit(self.product_history_limit)
        return [self.history_to_public(document) async for document in cursor if document.get("_id") != self.meta_document_id]

    async def product_detail(self, product_id: str, viewer_id: str, permissions: dict) -> dict | None:
        """
        組出商品詳細頁資料。

        Args:
            product_id (str): "mining_collection:昆蟲化石"
            viewer_id (str): "410847926236086272"
            permissions (dict): "{'shop_edit_description': False}"

        Returns:
            detail (dict | None): "{'product': {'name': '昆蟲化石'}}"
        """
        product = await self.get_product(product_id)
        if product is None:
            return None
        buy_orders = await self.list_open_orders(product_id, self.side_buy)
        sell_orders = await self.list_open_orders(product_id, self.side_sell)
        owned = await self.get_owned_count(viewer_id, product)
        my_buy_orders = [order for order in buy_orders if str(order.get("user_id")) == str(viewer_id)]
        stats = {
            "buy_count": len(buy_orders),
            "highest_buy_price": max((int(order["price"]) for order in buy_orders), default=None),
            "lowest_sell_price": min((int(order["price"]) for order in sell_orders), default=None),
        }
        return {
            "product": {
                "product_id": product["product_id"],
                "category": product.get("category"),
                "name": product.get("name") or product["product_id"],
                "description": str(product.get("description") or ""),
                "kind": product.get("kind"),
                "owned": owned,
                "owned_label": self.owned_label(owned),
                "can_sell": self.can_create_sell(viewer_id, product),
                "can_edit_description": bool(permissions.get("shop_edit_description")),
                "unlimited_stock": bool((product.get("flags") or {}).get("unlimited_stock")),
            },
            "buy_orders": [self.order_to_public(order, viewer_id) for order in buy_orders],
            "my_buy_orders": [self.order_to_public(order, viewer_id) for order in my_buy_orders],
            "sell_orders": [self.order_to_public(order, viewer_id) for order in sell_orders],
            "buy_order_count": stats["buy_count"],
            "highest_buy_price": stats["highest_buy_price"],
            "lowest_sell_price": stats["lowest_sell_price"],
            "recent_trades": await self.list_product_history(product_id),
        }

    def parse_price_quantity(self, price, quantity) -> tuple[int, int]:
        """
        檢查價格與數量為正整數。

        Args:
            price: "5000"
            quantity: "2"

        Returns:
            values (tuple): "(5000, 2)"
        """
        parsed_price = int(price)
        parsed_quantity = int(quantity)
        if parsed_price < 1 or parsed_quantity < 1:
            raise ValueError("價格與數量必須為正整數")
        return parsed_price, parsed_quantity

    async def create_buy_order(self, product_id: str, user_id: str, price, quantity, display_name: str) -> dict:
        """
        建立求購並預扣蛋糕。

        Args:
            product_id (str): "mining_collection:昆蟲化石"
            user_id (str): "410847926236086272"
            price: "5000"
            quantity: "2"
            display_name (str): "ani"

        Returns:
            result (dict): "{'ok': True}"
        """
        try:
            parsed_price, parsed_quantity = self.parse_price_quantity(price, quantity)
        except Exception:
            return {"ok": False, "error": "價格與數量必須為正整數"}
        reserved_cake = parsed_price * parsed_quantity
        async with self.lock:
            product = await self.get_product(product_id)
            if product is None:
                return {"ok": False, "error": "找不到這個商品"}
            if product.get("kind") == self.kind_animation_color:
                if parsed_quantity != 1:
                    return {"ok": False, "error": "這個商品一次只能求購 1 個"}
                if await self.already_owns_animation_color(user_id):
                    return {"ok": False, "error": "你已經擁有動態顏色身份組使用權"}
            stats = await self.market_stats(product_id)
            if stats["lowest_sell_price"] is not None and parsed_price >= stats["lowest_sell_price"]:
                return {"ok": False, "error": "求購價必須低於目前最便宜的賣單，不然直接購買即可"}
            if not await self.spend_cake(user_id, reserved_cake):
                return {"ok": False, "error": f"{common.cake_emoji}不足，無法求購"}
            order_id = await self.allocate_id("shop_order", "next_order_id")
            document = {
                "_id": str(order_id),
                "order_id": order_id,
                "side": self.side_buy,
                "product_id": product_id,
                "product_name": product.get("name") or product_id,
                "user_id": str(user_id),
                "user_name": display_name or self.resolve_name(user_id),
                "price": parsed_price,
                "quantity": parsed_quantity,
                "reserved_cake": reserved_cake,
                "status": self.order_status_open,
                "created_at": self.now_iso(),
            }
            await common.mongo_storage.get_collection("shop_order").insert_one(document)
        return {"ok": True, "order_id": order_id}

    async def cancel_buy_order(self, order_id: int, user_id: str) -> dict:
        """
        取消自己的求購並退回預扣蛋糕。

        Args:
            order_id (int): "1"
            user_id (str): "410847926236086272"

        Returns:
            result (dict): "{'ok': True}"
        """
        async with self.lock:
            collection = common.mongo_storage.get_collection("shop_order")
            order = await collection.find_one({"_id": str(order_id)})
            if order is None or order.get("side") != self.side_buy or order.get("status") != self.order_status_open:
                return {"ok": False, "error": "找不到這筆求購單"}
            if str(order.get("user_id")) != str(user_id):
                return {"ok": False, "error": "只能取消自己的求購單"}
            reserved_cake = int(order.get("reserved_cake") or 0)
            await collection.update_one(
                {"_id": str(order_id)},
                {"$set": {"status": self.order_status_cancelled, "quantity": 0, "reserved_cake": 0, "closed_at": self.now_iso()}},
            )
            await self.add_cake(user_id, reserved_cake)
        return {"ok": True}

    async def create_sell_order(self, product_id: str, user_id: str, price, quantity, display_name: str) -> dict:
        """
        建立賣單並預扣道具。

        Args:
            product_id (str): "mining_collection:昆蟲化石"
            user_id (str): "410847926236086272"
            price: "8000"
            quantity: "1"
            display_name (str): "ani"

        Returns:
            result (dict): "{'ok': True}"
        """
        try:
            parsed_price, parsed_quantity = self.parse_price_quantity(price, quantity)
        except Exception:
            return {"ok": False, "error": "價格與數量必須為正整數"}
        async with self.lock:
            product = await self.get_product(product_id)
            if product is None:
                return {"ok": False, "error": "找不到這個商品"}
            if not self.can_create_sell(user_id, product):
                return {"ok": False, "error": "你不能販賣這個商品"}
            stats = await self.market_stats(product_id)
            if stats["highest_buy_price"] is not None and parsed_price <= stats["highest_buy_price"]:
                return {"ok": False, "error": "售價必須高於目前最高的求購單，不然請用快速販賣"}
            if not await self.reserve_item(user_id, product, parsed_quantity):
                owned = await self.get_owned_count(user_id, product)
                owned_text = self.owned_label(owned)
                return {"ok": False, "error": f"你沒有足夠的{product.get('name') or '商品'}（目前持有 {owned_text}）"}
            order_id = await self.allocate_id("shop_order", "next_order_id")
            document = {
                "_id": str(order_id),
                "order_id": order_id,
                "side": self.side_sell,
                "product_id": product_id,
                "product_name": product.get("name") or product_id,
                "user_id": str(user_id),
                "user_name": display_name or self.resolve_name(user_id),
                "price": parsed_price,
                "quantity": parsed_quantity,
                "reserved_cake": 0,
                "status": self.order_status_open,
                "created_at": self.now_iso(),
            }
            await common.mongo_storage.get_collection("shop_order").insert_one(document)
        return {"ok": True, "order_id": order_id}

    async def cancel_sell_order(self, order_id: int, user_id: str) -> dict:
        """
        下架自己的賣單並歸還道具。

        Args:
            order_id (int): "2"
            user_id (str): "410847926236086272"

        Returns:
            result (dict): "{'ok': True}"
        """
        async with self.lock:
            collection = common.mongo_storage.get_collection("shop_order")
            order = await collection.find_one({"_id": str(order_id)})
            if order is None or order.get("side") != self.side_sell or order.get("status") != self.order_status_open:
                return {"ok": False, "error": "找不到這筆賣單"}
            if str(order.get("user_id")) != str(user_id):
                return {"ok": False, "error": "只能下架自己的商品"}
            product = await self.get_product(str(order.get("product_id") or ""))
            if product is None:
                return {"ok": False, "error": "找不到這個商品"}
            quantity = int(order.get("quantity") or 0)
            await collection.update_one(
                {"_id": str(order_id)},
                {"$set": {"status": self.order_status_cancelled, "quantity": 0, "closed_at": self.now_iso()}},
            )
            await self.release_item(user_id, product, quantity)
        return {"ok": True}

    async def write_history(self, *, product: dict, seller_id: str, seller_name: str, buyer_id: str,
                            buyer_name: str, price: int, quantity: int, trade_kind: str,
                            fee: int = 0, fee_percent: float = 0, seller_gain: int | None = None):
        """
        寫入成交紀錄。

        Args:
            product (dict): "{'product_id': 'mining_collection:昆蟲化石'}"
            seller_id (str): "4108"
            seller_name (str): "ani"
            buyer_id (str): "1234"
            buyer_name (str): "xu6"
            price (int): "5000"
            quantity (int): "1"
            trade_kind (str): "listing_buy"
            fee (int): "250"
            fee_percent (float): "5.0"
            seller_gain (int | None): "4750"
        """
        history_id = await self.allocate_id("shop_history", "next_history_id")
        total = price * quantity
        document = {
            "_id": str(history_id),
            "history_id": history_id,
            "product_id": product["product_id"],
            "product_name": product.get("name") or product["product_id"],
            "seller_id": str(seller_id),
            "seller_name": seller_name,
            "buyer_id": str(buyer_id),
            "buyer_name": buyer_name,
            "price": price,
            "quantity": quantity,
            "total": total,
            "fee": fee,
            "fee_percent": fee_percent,
            "seller_gain": total - fee if seller_gain is None else seller_gain,
            "kind": trade_kind,
            "created_at": self.now_iso(),
        }
        await common.mongo_storage.get_collection("shop_history").insert_one(document)

    def history_to_public(self, document: dict) -> dict:
        """
        轉成網頁用成交紀錄。

        Args:
            document (dict): "{'history_id': 1}"

        Returns:
            payload (dict): "{'product_name': '昆蟲化石'}"
        """
        seller_gain = document.get("seller_gain")
        if seller_gain is None:
            seller_gain = int(document.get("total") or 0) - int(document.get("fee") or 0)
        return {
            "history_id": int(document.get("history_id") or 0),
            "product_id": document.get("product_id"),
            "product_name": document.get("product_name"),
            "seller_id": str(document.get("seller_id") or ""),
            "seller_name": document.get("seller_name") or self.resolve_name(document.get("seller_id")),
            "buyer_id": str(document.get("buyer_id") or ""),
            "buyer_name": document.get("buyer_name") or self.resolve_name(document.get("buyer_id")),
            "price": int(document.get("price") or 0),
            "quantity": int(document.get("quantity") or 0),
            "total": int(document.get("total") or 0),
            "fee": int(document.get("fee") or 0),
            "fee_percent": float(document.get("fee_percent") or 0),
            "fee_percent_text": self.format_fee_percent(document.get("fee_percent") or 0),
            "seller_gain": int(seller_gain),
            "kind": document.get("kind"),
            "created_at": document.get("created_at") or "",
        }

    async def close_or_reduce_order(self, order: dict, fill_quantity: int, extra_fields: dict | None = None):
        """
        依成交數量減少掛單，賣完就關閉。

        Args:
            order (dict): "{'order_id': 1, 'quantity': 3}"
            fill_quantity (int): "1"
            extra_fields (dict | None): "{'reserved_cake': 0}"
        """
        remaining = int(order.get("quantity") or 0) - fill_quantity
        fields = extra_fields.copy() if extra_fields else {}
        fields["quantity"] = remaining
        if remaining <= 0:
            fields["status"] = self.order_status_filled
            fields["quantity"] = 0
            fields["closed_at"] = self.now_iso()
        await common.mongo_storage.get_collection("shop_order").update_one(
            {"_id": str(order["order_id"])},
            {"$set": fields},
        )

    async def buy_listing(self, order_id: int, buyer_id: str, quantity, display_name: str) -> dict:
        """
        購買一筆賣單（可指定數量）。

        Args:
            order_id (int): "2"
            buyer_id (str): "1234"
            quantity: "1"
            display_name (str): "xu6"

        Returns:
            result (dict): "{'ok': True}"
        """
        try:
            fill_quantity = int(quantity)
            if fill_quantity < 1:
                raise ValueError("數量必須為正整數")
        except Exception:
            return {"ok": False, "error": "數量必須為正整數"}
        async with self.lock:
            collection = common.mongo_storage.get_collection("shop_order")
            order = await collection.find_one({"_id": str(order_id)})
            if order is None or order.get("side") != self.side_sell or order.get("status") != self.order_status_open:
                return {"ok": False, "error": "找不到這筆賣單"}
            if str(order.get("user_id")) == str(buyer_id):
                return {"ok": False, "error": "不能購買自己上架的商品"}
            remaining = int(order.get("quantity") or 0)
            if fill_quantity > remaining:
                return {"ok": False, "error": f"這筆賣單只剩 {remaining} 個"}
            product = await self.get_product(str(order.get("product_id") or ""))
            if product is None:
                return {"ok": False, "error": "找不到這個商品"}
            if product.get("kind") == self.kind_animation_color:
                if fill_quantity != 1:
                    return {"ok": False, "error": "這個商品一次只能購買 1 個"}
                if await self.already_owns_animation_color(buyer_id):
                    return {"ok": False, "error": "你已經擁有動態顏色身份組使用權"}
            unit_price = int(order.get("price") or 0)
            total = unit_price * fill_quantity
            if not await self.spend_cake(buyer_id, total):
                return {"ok": False, "error": f"{common.cake_emoji}不足，無法購買"}
            seller_id = str(order.get("user_id"))
            try:
                delivered = await self.deliver_item(buyer_id, product, fill_quantity)
                if not delivered:
                    await self.add_cake(buyer_id, total)
                    return {"ok": False, "error": "發放商品失敗"}
                seller_gain, fee, fee_percent = await self.settle_trade_cake(seller_id, total)
                await self.close_or_reduce_order(order, fill_quantity)
                await self.write_history(
                    product=product,
                    seller_id=seller_id,
                    seller_name=order.get("user_name") or self.resolve_name(seller_id),
                    buyer_id=buyer_id,
                    buyer_name=display_name or self.resolve_name(buyer_id),
                    price=unit_price,
                    quantity=fill_quantity,
                    trade_kind=self.trade_kind_listing,
                    fee=fee,
                    fee_percent=fee_percent,
                    seller_gain=seller_gain,
                )
            except Exception:
                await self.add_cake(buyer_id, total)
                raise
        return {"ok": True, "price": unit_price, "quantity": fill_quantity}

    def highest_other_buy_order(self, orders: list[dict], user_id: str) -> dict | None:
        """
        找出不是自己的最高求購單。

        Args:
            orders (list): "[{'price': 100}]"
            user_id (str): "4108"

        Returns:
            order (dict | None): "{'price': 100}"
        """
        for order in orders:
            if str(order.get("user_id")) != str(user_id):
                return order
        return None

    async def quick_sell(self, product_id: str, seller_id: str, quantity, display_name: str) -> dict:
        """
        以目前最高求購價立刻賣出。

        Args:
            product_id (str): "mining_collection:昆蟲化石"
            seller_id (str): "4108"
            quantity: "1"
            display_name (str): "ani"

        Returns:
            result (dict): "{'ok': True}"
        """
        try:
            requested = int(quantity)
            if requested < 1:
                raise ValueError("數量必須為正整數")
        except Exception:
            return {"ok": False, "error": "數量必須為正整數"}
        async with self.lock:
            product = await self.get_product(product_id)
            if product is None:
                return {"ok": False, "error": "找不到這個商品"}
            if not self.can_create_sell(seller_id, product):
                return {"ok": False, "error": "你不能販賣這個商品"}
            buy_orders = await self.list_open_orders(product_id, self.side_buy)
            target = self.highest_other_buy_order(buy_orders, seller_id)
            if target is None:
                return {"ok": False, "error": "目前沒有其他玩家的求購單"}
            remaining = int(target.get("quantity") or 0)
            fill_quantity = min(requested, remaining)
            if product.get("kind") == self.kind_animation_color:
                fill_quantity = min(fill_quantity, 1)
                if await self.already_owns_animation_color(str(target.get("user_id"))):
                    return {"ok": False, "error": "對方已經擁有動態顏色身份組使用權"}
            if fill_quantity < 1:
                return {"ok": False, "error": "這筆求購單已經沒有剩餘數量"}
            owned = await self.get_owned_count(seller_id, product)
            if owned is not None and fill_quantity > owned:
                return {"ok": False, "error": f"你只有 {owned} 個{product.get('name') or '商品'}"}
            if not await self.reserve_item(seller_id, product, fill_quantity):
                return {"ok": False, "error": f"你沒有足夠的{product.get('name') or '商品'}"}
            buyer_id = str(target.get("user_id"))
            unit_price = int(target.get("price") or 0)
            total = unit_price * fill_quantity
            reserved_cake = int(target.get("reserved_cake") or 0)
            if reserved_cake < total:
                await self.release_item(seller_id, product, fill_quantity)
                return {"ok": False, "error": "求購單預扣蛋糕不足"}
            delivered = await self.deliver_item(buyer_id, product, fill_quantity)
            if not delivered:
                await self.release_item(seller_id, product, fill_quantity)
                return {"ok": False, "error": "發放商品失敗"}
            seller_gain, fee, fee_percent = await self.settle_trade_cake(seller_id, total)
            await self.close_or_reduce_order(target, fill_quantity, {"reserved_cake": reserved_cake - total})
            await self.write_history(
                product=product,
                seller_id=seller_id,
                seller_name=display_name or self.resolve_name(seller_id),
                buyer_id=buyer_id,
                buyer_name=target.get("user_name") or self.resolve_name(buyer_id),
                price=unit_price,
                quantity=fill_quantity,
                trade_kind=self.trade_kind_quick,
                fee=fee,
                fee_percent=fee_percent,
                seller_gain=seller_gain,
            )
        return {"ok": True, "price": unit_price, "quantity": fill_quantity}

    async def update_description(self, product_id: str, description: str) -> dict:
        """
        修改商品描述。

        Args:
            product_id (str): "mining_collection:昆蟲化石"
            description (str): "森林礦坑的收藏品"

        Returns:
            result (dict): "{'ok': True}"
        """
        product = await self.get_product(product_id)
        if product is None:
            return {"ok": False, "error": "找不到這個商品"}
        text = str(description or "").strip()
        if len(text) > 2000:
            return {"ok": False, "error": "描述最多 2000 字"}
        await common.mongo_storage.get_collection("shop_product").update_one(
            {"$or": [{"_id": product_id}, {"product_id": product_id}]},
            {"$set": {"description": text}},
        )
        return {"ok": True}

    async def list_my_history(self, user_id: str) -> list[dict]:
        """
        自己的買賣成交紀錄。

        Args:
            user_id (str): "410847926236086272"

        Returns:
            items (list): "[{'product_name': '昆蟲化石'}]"
        """
        collection = common.mongo_storage.get_collection("shop_history")
        cursor = collection.find(
            {"$or": [{"buyer_id": str(user_id)}, {"seller_id": str(user_id)}]}
        ).sort("created_at", -1).limit(self.history_limit)
        return [self.history_to_public(document) async for document in cursor if document.get("_id") != self.meta_document_id]


class Shop(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.bot = client
        self.shop_house = ShopHouse(client)
        self.prepare_task: asyncio.Task | None = None
        client.shop_house = self.shop_house

    async def cog_load(self):
        """建立索引並補齊初版商品。"""
        self.prepare_task = asyncio.create_task(self.prepare_shop())

    async def cog_unload(self):
        """取消商店初始化工作。"""
        if self.prepare_task is None:
            return
        self.prepare_task.cancel()
        self.prepare_task = None

    async def prepare_shop(self):
        """等 bot ready 後建立索引與商品目錄。"""
        await self.bot.wait_until_ready()
        await self.shop_house.ensure_indexes()
        await self.shop_house.ensure_catalog()

    @app_commands.command(name="shop", description="開啟商店互動面板")
    async def shop(self, interaction: discord.Interaction):
        """給出商店網頁連結。"""
        embed = Embed(title="商店", description="點下方按鈕前往商店互動面板，可以買賣伺服器道具與挖礦收藏品。", color=common.bot_color)
        await interaction.response.send_message(embed=embed, view=ShopLinkView(self.shop_house.page_url()))


async def setup(client: commands.Bot):
    await client.add_cog(Shop(client))
