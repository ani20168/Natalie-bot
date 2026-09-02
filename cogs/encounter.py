import random
import uuid
from datetime import datetime, timedelta, timezone

import discord
from discord import Embed, app_commands
from discord.ext import commands

from . import common


class EncounterHouse:
    """挖礦奇遇任務、進度與獎勵。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings_document_id = "settings"
        self.dataset_name = "mining_encounter"
        self.difficulty_easy = "easy"
        self.difficulty_hard = "hard"
        self.difficulty_legendary = "legendary"
        self.difficulty_keys = [self.difficulty_easy, self.difficulty_hard, self.difficulty_legendary]
        self.difficulty_labels = {
            self.difficulty_easy: "簡單",
            self.difficulty_hard: "困難",
            self.difficulty_legendary: "傳奇",
        }
        self.daily_limit = 3
        self.reset_hour = 6
        self.slider_min = 0
        self.slider_max = 100
        self.slider_default = 50
        self.default_easy_weight = 60
        self.default_hard_weight = 30
        self.default_legendary_weight = 10
        self.default_quest_name = "未命名奇遇"
        self.hidden_collection_mark = "???"
        self.empty_message = "這裡風平浪靜...什麼事情都沒有發生。"
        self.submit_fail_message = "哎呀，你好像沒有滿足他要的需求哦!"
        self.bag_full_message = "你的背包已滿，無法收下獎勵。"
        self.ended_message = "這次奇遇已經結束了。"
        self.button_label_max = 80
        self.submit_inflight = set()

    def mining_cog(self):
        """
        取得挖礦 cog。

        Returns:
            mining_cog (MiningGame | None): "MiningGame(...)"
        """
        return self.bot.get_cog("MiningGame")

    def all_collection_names(self) -> list[str]:
        """
        全部挖礦收藏品名稱。

        Returns:
            names (list): "['火龍遺骨', '地獄辣炒年糕']"
        """
        mining_cog = self.mining_cog()
        if mining_cog is None:
            return []
        names = []
        for item_list in mining_cog.collection_list.values():
            names.extend(item_list)
        return names

    def reward_item_catalog(self) -> list[dict]:
        """
        可作為奇遇獎勵的伺服器道具（不含動態身份組）。

        Returns:
            items (list): "[{'item_id': 'milk', 'name': '牛奶'}]"
        """
        item_house = getattr(self.bot, "server_item_house", None)
        if item_house is None:
            return []
        items = []
        for item_id, item in item_house.items.items():
            items.append({"item_id": item_id, "name": str(item.get("name") or item_id)})
        return items

    def default_difficulty_weights(self) -> dict:
        """
        難度拉桿預設權重。

        Returns:
            weights (dict): "{'easy': 60, 'hard': 30, 'legendary': 10}"
        """
        return {
            self.difficulty_easy: self.default_easy_weight,
            self.difficulty_hard: self.default_hard_weight,
            self.difficulty_legendary: self.default_legendary_weight,
        }

    def default_reward_weights(self) -> dict:
        """
        獎勵拉桿預設權重（全部公平）。

        Returns:
            weights (dict): "{'milk': 50}"
        """
        return {item["item_id"]: self.slider_default for item in self.reward_item_catalog()}

    def clamp_weight(self, value) -> int:
        """
        把拉桿值限制在 0～最大值。

        Args:
            value: "50"

        Returns:
            weight (int): "50"
        """
        try:
            number = int(value)
        except (TypeError, ValueError):
            return self.slider_min
        return max(self.slider_min, min(self.slider_max, number))

    def normalize_difficulty_weights(self, raw) -> dict:
        """
        補齊並限制難度權重。

        Args:
            raw: "{'easy': 60}"

        Returns:
            weights (dict): "{'easy': 60, 'hard': 30, 'legendary': 10}"
        """
        source = raw if isinstance(raw, dict) else {}
        defaults = self.default_difficulty_weights()
        weights = {}
        for key in self.difficulty_keys:
            if key in source:
                weights[key] = self.clamp_weight(source.get(key))
            else:
                weights[key] = defaults[key]
        return weights

    def normalize_reward_weights(self, raw) -> dict:
        """
        依目前道具清單補齊獎勵權重，未設定的新道具為 0。

        Args:
            raw: "{'milk': 50}"

        Returns:
            weights (dict): "{'milk': 50, 'magnet': 0}"
        """
        source = raw if isinstance(raw, dict) else {}
        weights = {}
        for item in self.reward_item_catalog():
            item_id = item["item_id"]
            if item_id in source:
                weights[item_id] = self.clamp_weight(source.get(item_id))
            else:
                weights[item_id] = self.slider_min
        return weights

    def weight_percents(self, weights: dict) -> dict:
        """
        把權重換成顯示用百分比。

        Args:
            weights (dict): "{'easy': 60, 'hard': 30, 'legendary': 10}"

        Returns:
            percents (dict): "{'easy': 60.0}"
        """
        total = sum(int(value) for value in weights.values())
        if total <= 0:
            count = len(weights)
            even = round(100 / count, 1) if count else 0
            return {key: even for key in weights}
        return {key: round(int(value) / total * 100, 1) for key, value in weights.items()}

    def pick_weighted_key(self, weights: dict) -> str | None:
        """
        依權重抽出一個鍵；全為 0 時改為平均抽。

        Args:
            weights (dict): "{'easy': 60, 'hard': 30}"

        Returns:
            key (str | None): "easy"
        """
        entries = [(key, int(weight)) for key, weight in weights.items() if int(weight) > 0]
        if not entries:
            keys = list(weights.keys())
            if not keys:
                return None
            return random.choice(keys)
        keys = [key for key, _ in entries]
        values = [weight for _, weight in entries]
        return random.choices(keys, weights=values, k=1)[0]

    def encounter_day_key(self) -> str:
        """
        以每天早上重置時刻切分的日期鍵。

        Returns:
            day_key (str): "2026-09-02"
        """
        nowtime = datetime.now(timezone(timedelta(hours=8)))
        if nowtime.hour < self.reset_hour:
            nowtime = nowtime - timedelta(days=1)
        return nowtime.strftime("%Y-%m-%d")

    def sync_user_day(self, user_data: dict) -> bool:
        """
        跨日則清空當日奇遇進度。

        Args:
            user_data (dict): "{'encounter_day': '2026-09-01'}"

        Returns:
            changed (bool): "True"
        """
        day_key = self.encounter_day_key()
        if user_data.get("encounter_day") == day_key:
            return False
        user_data["encounter_day"] = day_key
        user_data["encounter_used_ids"] = []
        user_data["encounter_active"] = None
        return True

    def used_quest_ids(self, user_data: dict) -> list[str]:
        """
        今日已完成的奇遇 ID。

        Args:
            user_data (dict): "{'encounter_used_ids': ['ab12']}"

        Returns:
            used_ids (list): "['ab12']"
        """
        used_ids = user_data.get("encounter_used_ids")
        if not isinstance(used_ids, list):
            return []
        return [str(quest_id) for quest_id in used_ids if quest_id]

    def is_quest_ready(self, quest: dict) -> bool:
        """
        任務是否已設定完整、可被玩家抽到。

        Args:
            quest (dict): "{'story_paragraphs': ['...']}"

        Returns:
            ready (bool): "True"
        """
        if not quest.get("story_paragraphs"):
            return False
        if not quest.get("requirements"):
            return False
        reward_weights = quest.get("reward_weights") or {}
        return any(int(weight) > 0 for weight in reward_weights.values())

    def requirement_need_text(self, requirements: list[dict]) -> str:
        """
        劇情結尾「需要」欄位文字。

        Args:
            requirements (list): "[{'quantity': 1}]"

        Returns:
            text (str): "??? x1"
        """
        return "\n".join(f"{self.hidden_collection_mark} x{entry['quantity']}" for entry in requirements)

    def submit_button_label(self, requirements: list[dict]) -> str:
        """
        提交按鈕標籤。

        Args:
            requirements (list): "[{'quantity': 1}, {'quantity': 2}]"

        Returns:
            label (str): "提交??? x1+??? x2"
        """
        parts = [f"{self.hidden_collection_mark} x{entry['quantity']}" for entry in requirements]
        label = "提交" + "+".join(parts)
        if len(label) > self.button_label_max:
            return f"提交{self.hidden_collection_mark}"
        return label

    def has_requirements(self, collections: dict, requirements: list[dict]) -> bool:
        """
        玩家收藏品是否足夠提交。

        Args:
            collections (dict): "{'火龍遺骨': 2}"
            requirements (list): "[{'collection': '火龍遺骨', 'quantity': 1}]"

        Returns:
            enough (bool): "True"
        """
        owned = collections if isinstance(collections, dict) else {}
        for entry in requirements:
            if int(owned.get(entry["collection"]) or 0) < entry["quantity"]:
                return False
        return True

    def consume_requirements(self, collections: dict, requirements: list[dict]):
        """
        從收藏品扣掉任務需求。

        Args:
            collections (dict): "{'火龍遺骨': 2}"
            requirements (list): "[{'collection': '火龍遺骨', 'quantity': 1}]"
        """
        for entry in requirements:
            collection_name = entry["collection"]
            remain = int(collections.get(collection_name) or 0) - entry["quantity"]
            if remain > 0:
                collections[collection_name] = remain
            elif collection_name in collections:
                del collections[collection_name]

    def normalize_requirements(self, raw) -> list[dict]:
        """
        過濾合法收藏品需求。

        Args:
            raw: "[{'collection': '火龍遺骨', 'quantity': 1}]"

        Returns:
            requirements (list): "[{'collection': '火龍遺骨', 'quantity': 1}]"
        """
        valid_names = set(self.all_collection_names())
        requirements = []
        if not isinstance(raw, list):
            return requirements
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            collection_name = str(entry.get("collection") or "")
            try:
                quantity = int(entry.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            if collection_name not in valid_names or quantity < 1:
                continue
            requirements.append({"collection": collection_name, "quantity": quantity})
        return requirements

    def normalize_story_paragraphs(self, raw) -> list[str]:
        """
        去掉空白劇情段落。

        Args:
            raw: "['第一段', '']"

        Returns:
            paragraphs (list): "['第一段']"
        """
        if not isinstance(raw, list):
            return []
        paragraphs = []
        for paragraph in raw:
            text = str(paragraph).strip()
            if text:
                paragraphs.append(text)
        return paragraphs

    def normalize_quest(self, document: dict | None) -> dict | None:
        """
        把資料庫文件整理成任務。

        Args:
            document (dict | None): "{'_id': 'ab12'}"

        Returns:
            quest (dict | None): "{'id': 'ab12', 'name': '未命名奇遇'}"
        """
        if not isinstance(document, dict):
            return None
        quest_id = str(document.get("_id") or document.get("id") or "")
        if not quest_id or quest_id == self.settings_document_id:
            return None
        difficulty = document.get("difficulty")
        if difficulty not in self.difficulty_keys:
            difficulty = self.difficulty_easy
        name = str(document.get("name") or self.default_quest_name).strip() or self.default_quest_name
        quest = {
            "id": quest_id,
            "name": name,
            "difficulty": difficulty,
            "story_paragraphs": self.normalize_story_paragraphs(document.get("story_paragraphs")),
            "requirements": self.normalize_requirements(document.get("requirements")),
            "reward_weights": self.normalize_reward_weights(document.get("reward_weights")),
        }
        quest["ready"] = self.is_quest_ready(quest)
        return quest

    def build_story_embed(self, quest: dict, story_index: int) -> Embed:
        """
        組出目前段落的 embed。

        Args:
            quest (dict): "{'story_paragraphs': ['...']}"
            story_index (int): "0"

        Returns:
            embed (Embed): "Embed(...)"
        """
        paragraphs = quest.get("story_paragraphs") or []
        if not paragraphs:
            return Embed(title="挖礦奇遇", description=self.empty_message, color=common.bot_error_color)
        index = max(0, min(story_index, len(paragraphs) - 1))
        embed = Embed(title="挖礦奇遇", description=paragraphs[index], color=common.bot_color)
        if index < len(paragraphs) - 1:
            return embed
        embed.add_field(name="難度", value=self.difficulty_labels.get(quest.get("difficulty"), "簡單"), inline=True)
        embed.add_field(name="需要", value=self.requirement_need_text(quest.get("requirements") or []), inline=False)
        return embed

    def build_story_view(self, userid: str, quest: dict, story_index: int):
        """
        組出目前段落的按鈕。

        Args:
            userid (str): "410847926236086272"
            quest (dict): "{'story_paragraphs': ['...']}"
            story_index (int): "0"

        Returns:
            view (EncounterView): "EncounterView(...)"
        """
        paragraphs = quest.get("story_paragraphs") or []
        index = max(0, min(story_index, max(len(paragraphs) - 1, 0)))
        show_submit = bool(paragraphs) and index >= len(paragraphs) - 1
        return EncounterView(self, userid, quest["id"], show_submit, self.submit_button_label(quest.get("requirements") or []))

    async def load_settings(self) -> dict:
        """
        讀取難度機率設定。

        Returns:
            settings (dict): "{'difficulty_weights': {'easy': 60}}"
        """
        collection = common.mongo_storage.get_collection(self.dataset_name)
        document = await collection.find_one({"_id": self.settings_document_id}) or {}
        return {"difficulty_weights": self.normalize_difficulty_weights(document.get("difficulty_weights"))}

    async def save_settings(self, raw_weights) -> dict:
        """
        寫入難度機率設定。

        Args:
            raw_weights: "{'easy': 60}"

        Returns:
            result (dict): "{'ok': True}"
        """
        weights = self.normalize_difficulty_weights(raw_weights)
        collection = common.mongo_storage.get_collection(self.dataset_name)
        await collection.replace_one(
            {"_id": self.settings_document_id},
            {"_id": self.settings_document_id, "difficulty_weights": weights},
            upsert=True,
        )
        return {
            "ok": True,
            "settings": {
                "difficulty_weights": weights,
                "difficulty_percents": self.weight_percents(weights),
            },
        }

    async def load_quests(self) -> list[dict]:
        """
        讀取全部奇遇任務。

        Returns:
            quests (list): "[{'id': 'ab12'}]"
        """
        collection = common.mongo_storage.get_collection(self.dataset_name)
        quests = []
        async for document in collection.find({"_id": {"$ne": self.settings_document_id}}):
            quest = self.normalize_quest(document)
            if quest is not None:
                quests.append(quest)
        quests.sort(key=lambda quest: quest.get("name") or "")
        return quests

    async def get_quest(self, quest_id: str) -> dict | None:
        """
        讀取單一任務。

        Args:
            quest_id (str): "ab12"

        Returns:
            quest (dict | None): "{'id': 'ab12'}"
        """
        if not quest_id:
            return None
        collection = common.mongo_storage.get_collection(self.dataset_name)
        document = await collection.find_one({"_id": quest_id})
        return self.normalize_quest(document)

    async def save_quest(self, payload: dict) -> dict:
        """
        新增或更新一個奇遇任務。

        Args:
            payload (dict): "{'name': '火山地底的低語'}"

        Returns:
            result (dict): "{'ok': True, 'quest': {'id': 'ab12'}}"
        """
        if not isinstance(payload, dict):
            return {"ok": False, "error": "任務資料格式錯誤"}
        quest_id = str(payload.get("id") or "").strip() or uuid.uuid4().hex
        name = str(payload.get("name") or self.default_quest_name).strip() or self.default_quest_name
        difficulty = payload.get("difficulty")
        if difficulty not in self.difficulty_keys:
            difficulty = self.difficulty_easy
        document = {
            "_id": quest_id,
            "name": name,
            "difficulty": difficulty,
            "story_paragraphs": self.normalize_story_paragraphs(payload.get("story_paragraphs")),
            "requirements": self.normalize_requirements(payload.get("requirements")),
            "reward_weights": self.normalize_reward_weights(payload.get("reward_weights")),
        }
        collection = common.mongo_storage.get_collection(self.dataset_name)
        await collection.replace_one({"_id": quest_id}, document, upsert=True)
        return {"ok": True, "quest": self.normalize_quest(document)}

    async def delete_quest(self, quest_id: str) -> dict:
        """
        刪除一個奇遇任務。

        Args:
            quest_id (str): "ab12"

        Returns:
            result (dict): "{'ok': True}"
        """
        quest_id = str(quest_id or "").strip()
        if not quest_id:
            return {"ok": False, "error": "找不到這個任務"}
        collection = common.mongo_storage.get_collection(self.dataset_name)
        result = await collection.delete_one({"_id": quest_id})
        if result.deleted_count < 1:
            return {"ok": False, "error": "找不到這個任務"}
        return {"ok": True}

    async def admin_payload(self) -> dict:
        """
        後台頁一次需要的資料。

        Returns:
            payload (dict): "{'ok': True, 'quests': []}"
        """
        settings = await self.load_settings()
        return {
            "ok": True,
            "settings": {
                "difficulty_weights": settings["difficulty_weights"],
                "difficulty_percents": self.weight_percents(settings["difficulty_weights"]),
            },
            "quests": await self.load_quests(),
            "collections": self.all_collection_names(),
            "reward_items": self.reward_item_catalog(),
            "difficulties": [{"key": key, "label": self.difficulty_labels[key]} for key in self.difficulty_keys],
            "slider_max": self.slider_max,
            "slider_default": self.slider_default,
            "default_quest_name": self.default_quest_name,
        }

    async def pick_quest(self, excluded_ids: list[str]) -> dict | None:
        """
        依難度機率抽任務；該難度沒有可接任務時改抽其他難度。

        Args:
            excluded_ids (list): "['ab12']"

        Returns:
            quest (dict | None): "{'id': 'cd34'}"
        """
        excluded = set(excluded_ids)
        quests = [quest for quest in await self.load_quests() if quest.get("ready") and quest["id"] not in excluded]
        if not quests:
            return None
        settings = await self.load_settings()
        rolled = self.pick_weighted_key(settings["difficulty_weights"])
        preferred = [quest for quest in quests if quest.get("difficulty") == rolled]
        pool = preferred if preferred else quests
        return random.choice(pool)

    async def handle_command(self, interaction: discord.Interaction):
        """
        處理 /encounter：接新任務或繼續未完成的奇遇。

        Args:
            interaction (discord.Interaction): Discord 指令互動
        """
        mining_cog = self.mining_cog()
        if mining_cog is None:
            await interaction.response.send_message(
                embed=Embed(title="挖礦奇遇", description="挖礦系統尚未就緒。", color=common.bot_error_color),
                ephemeral=True,
            )
            return

        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            mining_data = await mining_cog.miningdata_read(userid)
            user_data = mining_data[userid]
            self.sync_user_day(user_data)
            quest, story_index = await self.resolve_command_quest(user_data)
            await common.mongo_storage.upsert_user(userid, user_data, "mining")

        if quest is None:
            await interaction.response.send_message(
                embed=Embed(title="挖礦奇遇", description=self.empty_message, color=common.bot_error_color)
            )
            return
        await interaction.response.send_message(
            embed=self.build_story_embed(quest, story_index),
            view=self.build_story_view(userid, quest, story_index),
        )

    async def resolve_command_quest(self, user_data: dict) -> tuple[dict | None, int]:
        """
        決定這次指令要顯示的任務。呼叫端須已持有 jsonio_lock。

        Args:
            user_data (dict): "{'encounter_active': {'quest_id': 'ab12'}}"

        Returns:
            result (tuple): "(quest, 0)"
        """
        active = user_data.get("encounter_active")
        if isinstance(active, dict) and active.get("quest_id"):
            quest = await self.get_quest(str(active.get("quest_id")))
            if quest is not None and quest.get("ready"):
                try:
                    story_index = int(active.get("story_index") or 0)
                except (TypeError, ValueError):
                    story_index = 0
                return quest, max(0, story_index)
            user_data["encounter_active"] = None

        used_ids = self.used_quest_ids(user_data)
        if len(used_ids) >= self.daily_limit:
            return None, 0
        quest = await self.pick_quest(used_ids)
        if quest is None:
            return None, 0
        user_data["encounter_active"] = {"quest_id": quest["id"], "story_index": 0}
        return quest, 0

    async def handle_continue(self, interaction: discord.Interaction, userid: str, quest_id: str):
        """
        翻到下一段劇情。

        Args:
            interaction (discord.Interaction): 按鈕互動
            userid (str): "410847926236086272"
            quest_id (str): "ab12"
        """
        mining_cog = self.mining_cog()
        if mining_cog is None:
            await interaction.response.send_message(
                embed=Embed(title="挖礦奇遇", description="挖礦系統尚未就緒。", color=common.bot_error_color),
                ephemeral=True,
            )
            return

        async with common.jsonio_lock:
            mining_data = await mining_cog.miningdata_read(userid)
            user_data = mining_data[userid]
            self.sync_user_day(user_data)
            active = user_data.get("encounter_active")
            if not isinstance(active, dict) or str(active.get("quest_id")) != quest_id:
                await common.mongo_storage.upsert_user(userid, user_data, "mining")
                await interaction.response.send_message(
                    embed=Embed(title="挖礦奇遇", description=self.ended_message, color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            quest = await self.get_quest(quest_id)
            if quest is None or not quest.get("ready"):
                user_data["encounter_active"] = None
                await common.mongo_storage.upsert_user(userid, user_data, "mining")
                await interaction.response.send_message(
                    embed=Embed(title="挖礦奇遇", description=self.ended_message, color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            paragraphs = quest.get("story_paragraphs") or []
            try:
                story_index = int(active.get("story_index") or 0) + 1
            except (TypeError, ValueError):
                story_index = 1
            if story_index > len(paragraphs) - 1:
                story_index = max(len(paragraphs) - 1, 0)
            user_data["encounter_active"] = {"quest_id": quest_id, "story_index": story_index}
            await common.mongo_storage.upsert_user(userid, user_data, "mining")

        await interaction.response.edit_message(
            embed=self.build_story_embed(quest, story_index),
            view=self.build_story_view(userid, quest, story_index),
        )

    async def handle_submit(self, interaction: discord.Interaction, userid: str, quest_id: str):
        """
        檢查收藏品並發放獎勵。

        Args:
            interaction (discord.Interaction): 按鈕互動
            userid (str): "410847926236086272"
            quest_id (str): "ab12"
        """
        mining_cog = self.mining_cog()
        item_house = getattr(self.bot, "server_item_house", None)
        if mining_cog is None or item_house is None:
            await interaction.response.send_message(
                embed=Embed(title="挖礦奇遇", description="挖礦系統尚未就緒。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        inflight_key = f"{userid}:{quest_id}"
        if inflight_key in self.submit_inflight:
            await interaction.response.send_message(
                embed=Embed(title="挖礦奇遇", description=self.ended_message, color=common.bot_error_color),
                ephemeral=True,
            )
            return
        self.submit_inflight.add(inflight_key)
        try:
            await self.finish_submit(interaction, userid, quest_id, mining_cog, item_house)
        finally:
            self.submit_inflight.discard(inflight_key)

    async def finish_submit(self, interaction: discord.Interaction, userid: str, quest_id: str, mining_cog, item_house):
        """
        實際結算提交。呼叫端須已登記 inflight。

        Args:
            interaction (discord.Interaction): 按鈕互動
            userid (str): "410847926236086272"
            quest_id (str): "ab12"
            mining_cog: MiningGame
            item_house: ServerItemHouse
        """
        async with common.jsonio_lock:
            mining_data = await mining_cog.miningdata_read(userid)
            user_data = mining_data[userid]
            self.sync_user_day(user_data)
            active = user_data.get("encounter_active")
            if not isinstance(active, dict) or str(active.get("quest_id")) != quest_id:
                await common.mongo_storage.upsert_user(userid, user_data, "mining")
                await interaction.response.send_message(
                    embed=Embed(title="挖礦奇遇", description=self.ended_message, color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            quest = await self.get_quest(quest_id)
            if quest is None or not quest.get("ready"):
                user_data["encounter_active"] = None
                await common.mongo_storage.upsert_user(userid, user_data, "mining")
                await interaction.response.send_message(
                    embed=Embed(title="挖礦奇遇", description=self.ended_message, color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            requirements = quest.get("requirements") or []
            collections = user_data.get("collections")
            if not isinstance(collections, dict):
                collections = {}
                user_data["collections"] = collections
            if not self.has_requirements(collections, requirements):
                await common.mongo_storage.upsert_user(userid, user_data, "mining")
                await interaction.response.send_message(
                    embed=Embed(title="挖礦奇遇", description=self.submit_fail_message, color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            reward_id = self.pick_weighted_key(quest.get("reward_weights") or {})
            if not reward_id or reward_id not in item_house.items:
                await common.mongo_storage.upsert_user(userid, user_data, "mining")
                await interaction.response.send_message(
                    embed=Embed(title="挖礦奇遇", description="這個奇遇的獎勵設定有誤，請稍後再試。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            if not await item_house.can_receive(userid, reward_id):
                await common.mongo_storage.upsert_user(userid, user_data, "mining")
                await interaction.response.send_message(
                    embed=Embed(title="挖礦奇遇", description=self.bag_full_message, color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            if not await item_house.add_items(userid, reward_id, 1):
                await common.mongo_storage.upsert_user(userid, user_data, "mining")
                await interaction.response.send_message(
                    embed=Embed(title="挖礦奇遇", description=self.bag_full_message, color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            self.consume_requirements(collections, requirements)
            used_ids = self.used_quest_ids(user_data)
            used_ids.append(quest_id)
            user_data["encounter_used_ids"] = used_ids
            user_data["encounter_active"] = None
            await common.mongo_storage.upsert_user(userid, user_data, "mining")

        reward_name = item_house.item_display_name(reward_id)
        embed = Embed(title="挖礦奇遇", description="你成功完成了這次奇遇！", color=common.bot_color)
        embed.add_field(name="獎勵", value=f"獲得 **{reward_name}** x1", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)


class EncounterContinueButton(discord.ui.Button):
    """劇情「繼續」按鈕。"""

    def __init__(self):
        super().__init__(label="繼續", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        """翻到下一段劇情。"""
        await self.view.house.handle_continue(interaction, self.view.userid, self.view.quest_id)


class EncounterSubmitButton(discord.ui.Button):
    """劇情結尾提交收藏品按鈕。"""

    def __init__(self, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        """提交收藏品並結算獎勵。"""
        await self.view.house.handle_submit(interaction, self.view.userid, self.view.quest_id)


class EncounterView(discord.ui.View):
    """挖礦奇遇劇情按鈕。"""

    def __init__(self, house: EncounterHouse, userid: str, quest_id: str, show_submit: bool, submit_label: str):
        super().__init__(timeout=None)
        self.house = house
        self.userid = userid
        self.quest_id = quest_id
        if show_submit:
            self.add_item(EncounterSubmitButton(submit_label))
        else:
            self.add_item(EncounterContinueButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """只允許接任務的玩家按按鈕。"""
        if str(interaction.user.id) == self.userid:
            return True
        await interaction.response.send_message(
            embed=Embed(title="挖礦奇遇", description="這不是你的奇遇。", color=common.bot_error_color),
            ephemeral=True,
        )
        return False


class MiningEncounter(commands.Cog):
    """挖礦奇遇指令。"""

    def __init__(self, client: commands.Bot):
        self.bot = client
        self.encounter_house = EncounterHouse(client)
        client.encounter_house = self.encounter_house

    @app_commands.command(name="encounter", description="挖礦奇遇")
    async def encounter(self, interaction: discord.Interaction):
        """開啟當日挖礦奇遇劇情。"""
        await self.encounter_house.handle_command(interaction)


async def setup(client: commands.Bot):
    await client.add_cog(MiningEncounter(client))
