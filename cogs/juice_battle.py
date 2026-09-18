from discord import app_commands, Embed
from discord.ext import commands
from . import common
import discord
import random


class JuiceBattle(commands.Cog):
    """Juice Battle：角色對戰、裝備背包與挑戰流程。"""

    def __init__(self, client: commands.Bot):
        self.bot = client
        self.bag_size = 99
        self.bag_page_size = 10
        self.challenge_timeout = 120.0
        self.battle_timeout = 180.0
        self.bag_view_timeout = 180.0
        self.default_bet = 0
        self.leaderboard_min_rounds = 1
        self.leaderboard_top_n = 3
        self.default_character_id = "ownerless"
        self.starter_weapon_id = "wooden_stick"
        self.starter_armor_id = "leather_armor"
        self.characters = {
            "ownerless": {
                "name": "一無所有者",
                "hp": 10,
                "atk": 0,
                "defense": 0,
                "agi": 2,
                "ability": None,
            },
            "lily": {
                "name": "莉莉",
                "hp": 9,
                "atk": 3,
                "defense": 0,
                "agi": 2,
                "ability": {
                    "id": "poison",
                    "name": "中毒",
                    "phase": "attack",
                    "cd": 6,
                    "description": "本次攻擊成功時，賦予對方中毒：對方攻擊階段開始時 -1HP，持續 3 回合",
                },
            },
            "dashan": {
                "name": "大山",
                "hp": 11,
                "atk": 1,
                "defense": 3,
                "agi": -1,
                "ability": {
                    "id": "stance_swap",
                    "name": "調整架式",
                    "phase": "defend",
                    "cd": 3,
                    "description": "本回合攻擊與防禦對調（本次防守＋接著自己的攻擊）",
                },
            },
            "mike": {
                "name": "麥坤",
                "hp": 10,
                "atk": 1,
                "defense": 0,
                "agi": 3,
                "ability": {
                    "id": "fridge",
                    "name": "冰箱",
                    "phase": "defend",
                    "cd": None,
                    "description": "若本回合傷害會致死，則傷害無效並改為回復等量生命（每場一次）",
                },
            },
            "laura": {
                "name": "蘿拉",
                "hp": 10,
                "atk": 1,
                "defense": 2,
                "agi": 1,
                "ability": {
                    "id": "bind",
                    "name": "束縛",
                    "phase": "attack",
                    "cd": 3,
                    "description": "此次攻擊對手無法選擇閃避",
                },
            },
        }
        self.weapons = {
            "wooden_stick": {
                "name": "木棍",
                "hp_offset": 0,
                "atk_offset": 0,
                "def_offset": 0,
                "agi_offset": 0,
                "ability": None,
                "starter": True,
            },
        }
        self.armors = {
            "leather_armor": {
                "name": "皮甲",
                "hp_offset": 0,
                "atk_offset": 0,
                "def_offset": 0,
                "agi_offset": 0,
                "ability": None,
                "starter": True,
            },
        }

    async def cog_load(self):
        """
        載入時清除殘留對戰鎖，並盡力把舊對戰訊息標為作廢。
        """
        collection = common.mongo_storage.get_collection("userdata")
        if collection is None:
            return
        cursor = collection.find({"juice_battle.playing": True})
        async for document in cursor:
            session = (document.get("juice_battle") or {}).get("session") or {}
            channel_id = session.get("channel_id")
            message_id = session.get("message_id")
            if channel_id is None or message_id is None:
                continue
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(int(channel_id))
                except Exception:
                    continue
            try:
                message = await channel.fetch_message(int(message_id))
                embed = Embed(
                    title="Juice Battle",
                    description="因機器人重啟，本場戰鬥已作廢。",
                    color=common.bot_error_color,
                )
                await message.edit(embed=embed, view=None)
            except Exception:
                pass
        await collection.update_many(
            {"juice_battle.playing": True},
            {
                "$set": {"juice_battle.playing": False},
                "$unset": {"juice_battle.session": ""},
            },
        )

    def default_juice_battle(self) -> dict:
        """
        建立新玩家的預設 Juice Battle 資料。

        Returns:
            juice_battle (dict): "{'character_id': 'ownerless', 'bag': [...]}"
        """
        bag = [None] * self.bag_size
        bag[0] = {"item_id": self.starter_weapon_id, "kind": "weapon"}
        bag[1] = {"item_id": self.starter_armor_id, "kind": "armor"}
        return {
            "character_id": self.default_character_id,
            "bag": bag,
            "equipped_weapon_slot": 0,
            "equipped_armor_slot": 1,
            "playing": False,
            "character_stats": {},
        }

    def ensure_juice_battle(self, user_data: dict) -> dict:
        """
        確保 userdata 內有完整 juice_battle 欄位。

        Args:
            user_data (dict): "{'cake': 0}"

        Returns:
            juice_battle (dict): "{'character_id': 'ownerless'}"
        """
        juice_battle = user_data.get("juice_battle")
        if not isinstance(juice_battle, dict):
            juice_battle = self.default_juice_battle()
            user_data["juice_battle"] = juice_battle
            return juice_battle
        if juice_battle.get("character_id") not in self.characters:
            juice_battle["character_id"] = self.default_character_id
        bag = juice_battle.get("bag")
        if not isinstance(bag, list):
            bag = [None] * self.bag_size
        if len(bag) < self.bag_size:
            bag = bag + [None] * (self.bag_size - len(bag))
        elif len(bag) > self.bag_size:
            bag = bag[: self.bag_size]
        juice_battle["bag"] = bag
        if "equipped_weapon_slot" not in juice_battle:
            juice_battle["equipped_weapon_slot"] = None
        if "equipped_armor_slot" not in juice_battle:
            juice_battle["equipped_armor_slot"] = None
        if "playing" not in juice_battle:
            juice_battle["playing"] = False
        if not isinstance(juice_battle.get("character_stats"), dict):
            juice_battle["character_stats"] = {}
        user_data["juice_battle"] = juice_battle
        return juice_battle

    def item_template(self, kind: str, item_id: str) -> dict | None:
        """
        取得武器或防具靜態資料。

        Args:
            kind (str): "weapon"
            item_id (str): "wooden_stick"

        Returns:
            template (dict | None): "{'name': '木棍', 'starter': True}"
        """
        if kind == "weapon":
            return self.weapons.get(item_id)
        if kind == "armor":
            return self.armors.get(item_id)
        return None

    def offsets_from_juice(self, juice_battle: dict) -> dict:
        """
        依目前裝備計算四種偏移量。

        Args:
            juice_battle (dict): "{'bag': [], 'equipped_weapon_slot': 0}"

        Returns:
            offsets (dict): "{'hp_offset': 0, 'atk_offset': 0, 'def_offset': 0, 'agi_offset': 0}"
        """
        offsets = {"hp_offset": 0, "atk_offset": 0, "def_offset": 0, "agi_offset": 0}
        bag = juice_battle.get("bag") or []
        for slot_key in ("equipped_weapon_slot", "equipped_armor_slot"):
            slot = juice_battle.get(slot_key)
            if slot is None or slot < 0 or slot >= len(bag):
                continue
            entry = bag[slot]
            if not isinstance(entry, dict):
                continue
            template = self.item_template(entry.get("kind"), entry.get("item_id"))
            if template is None:
                continue
            offsets["hp_offset"] += template["hp_offset"]
            offsets["atk_offset"] += template["atk_offset"]
            offsets["def_offset"] += template["def_offset"]
            offsets["agi_offset"] += template["agi_offset"]
        return offsets

    def format_stat_block(self, character_id: str, juice_battle: dict) -> str:
        """
        組出角色素質顯示文字（基礎＋偏移）。

        Args:
            character_id (str): "lily"
            juice_battle (dict): "{'equipped_weapon_slot': 0}"

        Returns:
            text (str): "角色：莉莉\\n生命：9 (+0)"
        """
        character = self.characters[character_id]
        offsets = self.offsets_from_juice(juice_battle)
        return (
            f"角色：{character['name']}\n"
            f"生命：{character['hp']} ({offsets['hp_offset']:+d}) → {character['hp'] + offsets['hp_offset']}\n"
            f"攻擊：{character['atk']} ({offsets['atk_offset']:+d}) → {character['atk'] + offsets['atk_offset']}\n"
            f"防禦：{character['defense']} ({offsets['def_offset']:+d}) → {character['defense'] + offsets['def_offset']}\n"
            f"敏捷：{character['agi']} ({offsets['agi_offset']:+d}) → {character['agi'] + offsets['agi_offset']}"
        )

    def session_jump_url(self, session: dict | None) -> str:
        """
        產生對戰訊息跳轉連結。

        Args:
            session (dict | None): "{'guild_id': '1', 'channel_id': '2', 'message_id': '3'}"

        Returns:
            url (str): "https://discord.com/channels/1/2/3"
        """
        if not isinstance(session, dict):
            return ""
        guild_id = session.get("guild_id")
        channel_id = session.get("channel_id")
        message_id = session.get("message_id")
        if not guild_id or not channel_id or not message_id:
            return ""
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

    def playing_block_description(self, juice_battle: dict) -> str:
        """
        組出「仍在對戰中」的提示（含訊息連結）。

        Args:
            juice_battle (dict): "{'playing': True, 'session': {}}"

        Returns:
            text (str): "你還在對戰中。\\n對戰訊息：..."
        """
        url = self.session_jump_url(juice_battle.get("session"))
        if url:
            return f"你還在對戰中。\n對戰訊息：{url}"
        return "你還在對戰中。"

    def build_fighter(self, *, user_id: str, display_name: str, character_id: str, juice_battle: dict | None, is_bot: bool) -> dict:
        """
        建立戰鬥用角色狀態。

        Args:
            user_id (str): "4108"
            display_name (str): "Ani"
            character_id (str): "lily"
            juice_battle (dict | None): "{'bag': []}"
            is_bot (bool): "False"

        Returns:
            fighter (dict): "{'user_id': '4108', 'hp': 9, 'max_hp': 9}"
        """
        character = self.characters[character_id]
        if juice_battle is None:
            offsets = {"hp_offset": 0, "atk_offset": 0, "def_offset": 0, "agi_offset": 0}
        else:
            offsets = self.offsets_from_juice(juice_battle)
        max_hp = character["hp"] + offsets["hp_offset"]
        return {
            "user_id": str(user_id),
            "display_name": display_name,
            "character_id": character_id,
            "character_name": character["name"],
            "hp": max_hp,
            "max_hp": max_hp,
            "atk": character["atk"],
            "defense": character["defense"],
            "agi": character["agi"],
            "hp_offset": offsets["hp_offset"],
            "atk_offset": offsets["atk_offset"],
            "def_offset": offsets["def_offset"],
            "agi_offset": offsets["agi_offset"],
            "is_bot": is_bot,
            "skill_cd": 0,
            "skill_used_once": False,
            "skill_armed": False,
            "stance_swap_attack": False,
            "poison_remaining": 0,
        }

    def character_ability(self, character_id: str) -> dict | None:
        """
        取得角色技能定義。

        Args:
            character_id (str): "lily"

        Returns:
            ability (dict | None): "{'id': 'poison', 'name': '中毒', 'phase': 'attack', 'cd': 6}"
        """
        character = self.characters.get(character_id)
        if character is None:
            return None
        ability = character.get("ability")
        return ability if isinstance(ability, dict) else None

    def skill_is_ready(self, fighter: dict, phase: str) -> bool:
        """
        判斷該階段是否可發動技能。

        Args:
            fighter (dict): "{'character_id': 'lily', 'skill_cd': 0}"
            phase (str): "attack"

        Returns:
            ready (bool): "True"
        """
        ability = self.character_ability(fighter["character_id"])
        if ability is None or ability.get("phase") != phase:
            return False
        if ability.get("cd") is None:
            return not fighter.get("skill_used_once", False)
        return int(fighter.get("skill_cd", 0)) <= 0

    def consume_armed_skill(self, fighter: dict) -> dict | None:
        """
        消耗已發動的技能並進入 CD／一次性標記。

        Args:
            fighter (dict): "{'skill_armed': True, 'character_id': 'lily'}"

        Returns:
            ability (dict | None): "消耗的技能定義；未發動則 None"
        """
        if not fighter.get("skill_armed"):
            return None
        ability = self.character_ability(fighter["character_id"])
        fighter["skill_armed"] = False
        if ability is None:
            return None
        if ability.get("cd") is None:
            fighter["skill_used_once"] = True
        else:
            fighter["skill_cd"] = int(ability["cd"])
        return ability

    def attack_roll_stats(self, fighter: dict) -> tuple[int, int]:
        """
        取得攻擊擲骰用的基礎值與偏移（含大山架式對調）。

        Args:
            fighter (dict): "{'atk': 1, 'stance_swap_attack': True}"

        Returns:
            stats (tuple[int, int]): "(base, offset)"
        """
        if fighter.get("stance_swap_attack"):
            return fighter["defense"], fighter["def_offset"]
        return fighter["atk"], fighter["atk_offset"]

    def defense_roll_stats(self, fighter: dict, *, stance_swap_defend: bool) -> tuple[int, int]:
        """
        取得防禦擲骰用的基礎值與偏移。

        Args:
            fighter (dict): "{'defense': 3}"
            stance_swap_defend (bool): "True"

        Returns:
            stats (tuple[int, int]): "(base, offset)"
        """
        if stance_swap_defend:
            return fighter["atk"], fighter["atk_offset"]
        return fighter["defense"], fighter["def_offset"]

    def build_bot_fighter(self) -> dict:
        """
        建立 Natalie 戰鬥角色（隨機非預設角色＋初始裝備）。

        Returns:
            fighter (dict): "{'user_id': '...', 'is_bot': True}"
        """
        character_ids = [character_id for character_id in self.characters if character_id != self.default_character_id]
        character_id = random.choice(character_ids)
        fake_juice = {
            "bag": [
                {"item_id": self.starter_weapon_id, "kind": "weapon"},
                {"item_id": self.starter_armor_id, "kind": "armor"},
            ] + [None] * (self.bag_size - 2),
            "equipped_weapon_slot": 0,
            "equipped_armor_slot": 1,
        }
        return self.build_fighter(
            user_id=str(common.bot_id),
            display_name="Natalie",
            character_id=character_id,
            juice_battle=fake_juice,
            is_bot=True,
        )

    def roll_stat(self, base: int, offset: int) -> tuple[int, int]:
        """
        擲 1d6 並加上基礎值與偏移。

        Args:
            base (int): "3"
            offset (int): "2"

        Returns:
            result (tuple[int, int]): "(dice, total) 例如 (3, 8)"
        """
        dice = random.randint(1, 6)
        return dice, dice + base + offset

    async def load_user(self, userid: str) -> dict:
        """
        讀取並確保使用者文件存在。

        Args:
            userid (str): "4108"

        Returns:
            user_data (dict): "{'cake': 0, 'juice_battle': {}}"
        """
        user_data = await common.mongo_storage.get_user(userid)
        if user_data is None:
            await common.mongo_storage.ensure_user_document(userid)
            user_data = await common.mongo_storage.get_user(userid)
        self.ensure_juice_battle(user_data)
        return user_data

    async def clear_session(self, userid: str):
        """
        清除指定玩家的對戰中狀態。

        Args:
            userid (str): "4108"
        """
        user_data = await self.load_user(userid)
        user_data["juice_battle"]["playing"] = False
        user_data["juice_battle"].pop("session", None)
        await common.mongo_storage.replace_user(userid, user_data)

    async def set_playing_session(self, userid: str, session: dict):
        """
        標記玩家進入對戰並寫入 session。

        Args:
            userid (str): "4108"
            session (dict): "{'channel_id': '1', 'message_id': '2'}"
        """
        user_data = await self.load_user(userid)
        user_data["juice_battle"]["playing"] = True
        user_data["juice_battle"]["session"] = session
        await common.mongo_storage.replace_user(userid, user_data)

    async def record_character_result(self, fighter: dict, *, won: bool):
        """
        依該場使用的角色寫入勝場／場數（機器人略過）。

        Args:
            fighter (dict): "{'user_id': '4108', 'character_id': 'lily', 'is_bot': False}"
            won (bool): "True"
        """
        if fighter.get("is_bot"):
            return
        userid = str(fighter["user_id"])
        character_id = fighter.get("character_id")
        if character_id not in self.characters:
            return
        user_data = await self.load_user(userid)
        juice_battle = user_data["juice_battle"]
        stats_map = juice_battle.setdefault("character_stats", {})
        entry = stats_map.get(character_id)
        if not isinstance(entry, dict):
            entry = {"win": 0, "round": 0}
        entry["round"] = int(entry.get("round", 0)) + 1
        if won:
            entry["win"] = int(entry.get("win", 0)) + 1
        else:
            entry["win"] = int(entry.get("win", 0))
        stats_map[character_id] = entry
        juice_battle["character_stats"] = stats_map
        await common.mongo_storage.replace_user(userid, user_data)

    async def record_battle_outcome(self, winner: dict, loser: dict):
        """
        同時寫入勝負雙方的角色統計。

        Args:
            winner (dict): "{'user_id': '4108', 'character_id': 'lily'}"
            loser (dict): "{'user_id': '4109', 'character_id': 'mike'}"
        """
        await self.record_character_result(winner, won=True)
        await self.record_character_result(loser, won=False)

    def format_win_rate(self, win: int, round_count: int) -> str:
        """
        格式化勝率文字。

        Args:
            win (int): "3"
            round_count (int): "10"

        Returns:
            text (str): "30.0%"
        """
        if round_count <= 0:
            return "未知"
        return f"{(win / round_count):.1%}"

    async def notify_challenge_dm(self, opponent: discord.Member, challenger: discord.abc.User, jump_url: str):
        """
        私訊被挑戰者，附上挑戰訊息連結。

        Args:
            opponent (discord.Member): "被挑戰者"
            challenger (discord.abc.User): "挑戰者"
            jump_url (str): "https://discord.com/channels/..."
        """
        description = (
            f"**{challenger.display_name}** 向你發起了 Juice Battle 挑戰！\n"
            f"請點擊下方連結回到挑戰訊息，並按下「同意挑戰」。"
        )
        if jump_url:
            description += f"\n\n挑戰訊息：{jump_url}"
        embed = Embed(title="Juice Battle｜挑戰通知", description=description, color=common.bot_color)
        try:
            await opponent.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    def build_bag_embed(self, juice_battle: dict, page: int, discard_confirm_slot: int | None = None) -> Embed:
        """
        建立裝備背包 embed。

        Args:
            juice_battle (dict): "{'bag': []}"
            page (int): "0"
            discard_confirm_slot (int | None): "3"

        Returns:
            embed (Embed): "Juice Battle｜裝備背包"
        """
        max_page = (self.bag_size - 1) // self.bag_page_size
        page = max(0, min(page, max_page))
        start = page * self.bag_page_size
        end = min(start + self.bag_page_size, self.bag_size)
        embed = Embed(
            title="Juice Battle｜裝備背包",
            description=f"共 {self.bag_size} 格。第 **{page + 1}/{max_page + 1}** 頁。\n點「裝備 N」裝備該格；「丟棄 N」需再確認。初始武器／防具不可丟。",
            color=common.bot_color,
        )
        bag = juice_battle["bag"]
        weapon_slot = juice_battle.get("equipped_weapon_slot")
        armor_slot = juice_battle.get("equipped_armor_slot")
        for index in range(start, end):
            entry = bag[index]
            slot_label = index + 1
            if entry is None:
                embed.add_field(name=f"[{slot_label}] （空）", value="—", inline=False)
                continue
            template = self.item_template(entry.get("kind"), entry.get("item_id"))
            if template is None:
                embed.add_field(name=f"[{slot_label}] （未知）", value="—", inline=False)
                continue
            kind_text = "武器" if entry.get("kind") == "weapon" else "防具"
            tags = []
            if weapon_slot == index or armor_slot == index:
                tags.append("裝備中")
            if template.get("starter"):
                tags.append("初始")
            tag_text = f"（{'／'.join(tags)}）" if tags else ""
            value = (
                f"{kind_text}{tag_text}\n"
                f"生命偏移 {template['hp_offset']:+d}｜攻擊 {template['atk_offset']:+d}｜"
                f"防禦 {template['def_offset']:+d}｜敏捷 {template['agi_offset']:+d}"
            )
            embed.add_field(name=f"[{slot_label}] {template['name']}", value=value, inline=False)
        if discard_confirm_slot is not None:
            entry = bag[discard_confirm_slot] if 0 <= discard_confirm_slot < len(bag) else None
            name = "未知"
            if isinstance(entry, dict):
                template = self.item_template(entry.get("kind"), entry.get("item_id"))
                if template is not None:
                    name = template["name"]
            embed.add_field(
                name="丟棄確認",
                value=f"確定要丟棄第 **{discard_confirm_slot + 1}** 格的 **{name}** 嗎？此操作無法復原。",
                inline=False,
            )
        return embed

    def resolve_initiative(self, fighter_a: dict, fighter_b: dict) -> tuple[dict, dict, str]:
        """
        雙方投閃避骰決定先攻，平手重擲。

        Args:
            fighter_a (dict): "{'agi': 2, 'agi_offset': 0}"
            fighter_b (dict): "{'agi': 3, 'agi_offset': 0}"

        Returns:
            result (tuple): "(先攻方, 後攻方, 說明文字)"
        """
        while True:
            _dice_a, total_a = self.roll_stat(fighter_a["agi"], fighter_a["agi_offset"])
            _dice_b, total_b = self.roll_stat(fighter_b["agi"], fighter_b["agi_offset"])
            summary = (
                f"{fighter_a['display_name']} 先攻 **{total_a}**｜"
                f"{fighter_b['display_name']} 先攻 **{total_b}**"
            )
            if total_a > total_b:
                return fighter_a, fighter_b, f"{summary}\n**{fighter_a['display_name']}** 先攻！"
            if total_b > total_a:
                return fighter_b, fighter_a, f"{summary}\n**{fighter_b['display_name']}** 先攻！"

    def build_battle_embed(self, view: "JuiceBattleView") -> Embed:
        """
        依戰鬥 View 狀態組出 embed。

        Args:
            view (JuiceBattleView): "進行中的戰鬥 View"

        Returns:
            embed (Embed): "Juice Battle"
        """
        embed = Embed(title="Juice Battle", color=common.bot_color)
        for fighter in (view.fighter_a, view.fighter_b):
            ability = self.character_ability(fighter["character_id"])
            # 大山架式：技能已發動或對調攻擊尚未打完時，顯示對調後攻防
            stance_active = bool(fighter.get("stance_swap_attack")) or (
                bool(fighter.get("skill_armed")) and ability is not None and ability.get("id") == "stance_swap"
            )
            if stance_active:
                display_atk = fighter["defense"]
                display_def = fighter["atk"]
                display_atk_offset = fighter["def_offset"]
                display_def_offset = fighter["atk_offset"]
            else:
                display_atk = fighter["atk"]
                display_def = fighter["defense"]
                display_atk_offset = fighter["atk_offset"]
                display_def_offset = fighter["def_offset"]

            status_parts = []
            if fighter.get("poison_remaining", 0) > 0:
                status_parts.append(f"中毒剩餘 {fighter['poison_remaining']}")
            if fighter.get("skill_armed") and not stance_active:
                status_parts.append("技能已發動")
            if ability and ability.get("cd") is not None and int(fighter.get("skill_cd", 0)) > 0:
                status_parts.append(f"{ability['name']} CD {fighter['skill_cd']}")
            elif ability and ability.get("cd") is None and fighter.get("skill_used_once"):
                status_parts.append(f"{ability['name']} 已使用")
            status_text = f"\n狀態：{'／'.join(status_parts)}" if status_parts else ""
            ability_text = f"\n技能：{ability['name']}" if ability else ""
            embed.add_field(
                name=f"{fighter['display_name']}（{fighter['character_name']}）",
                value=(
                    f"HP **{fighter['hp']}/{fighter['max_hp']}**\n"
                    f"攻擊 {display_atk}({display_atk_offset:+d})｜"
                    f"防禦 {display_def}({display_def_offset:+d})｜"
                    f"敏捷 {fighter['agi']}({fighter['agi_offset']:+d})"
                    f"{ability_text}{status_text}"
                ),
                inline=False,
            )
        embed.add_field(name="賭注", value=f"{self.default_bet} {common.cake_emoji}", inline=False)
        if view.log_text:
            embed.add_field(name="戰鬥紀錄", value=view.log_text[:1024], inline=False)
        if view.phase == "ended":
            embed.add_field(name="結果", value=view.result_text or "戰鬥結束", inline=False)
        elif view.phase == "attack":
            attacker = view.fighter_by_id(view.attacker_id)
            action = f"輪到 **{attacker['display_name']}** 攻擊"
            if attacker.get("skill_armed"):
                ability = self.character_ability(attacker["character_id"])
                if ability:
                    action += f"\n已發動：**{ability['name']}**"
            embed.add_field(name="行動", value=action, inline=False)
        elif view.phase == "defend":
            defender = view.fighter_by_id(view.defender_id)
            if view.pending_bind:
                action = f"輪到 **{defender['display_name']}** 選擇防禦（被束縛，無法閃避）"
            else:
                action = f"輪到 **{defender['display_name']}** 選擇防禦或閃避"
            if defender.get("skill_armed"):
                ability = self.character_ability(defender["character_id"])
                if ability:
                    action += f"\n已發動：**{ability['name']}**"
            embed.add_field(name="行動", value=action, inline=False)
        return embed

    @app_commands.command(name="juice_battle_player", description="更換 Juice Battle 遊玩角色")
    async def juice_battle_player(self, interaction: discord.Interaction):
        """
        開啟角色選擇介面。

        Args:
            interaction (discord.Interaction): "slash 互動"
        """
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            user_data = await self.load_user(userid)
            juice_battle = user_data["juice_battle"]
            if juice_battle.get("playing"):
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle",
                        description=self.playing_block_description(juice_battle),
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
                return
            current_id = juice_battle["character_id"]
            await common.mongo_storage.replace_user(userid, user_data)

        current_name = self.characters[current_id]["name"]
        embed = Embed(
            title="Juice Battle｜更換角色",
            description=f"目前角色：**{current_name}**\n請選擇要使用的角色。",
            color=common.bot_color,
        )
        for character_id, character in self.characters.items():
            ability = character.get("ability")
            if isinstance(ability, dict):
                phase_text = "攻擊階段" if ability.get("phase") == "attack" else "防守階段"
                cd_value = ability.get("cd")
                cd_text = f"CD:{cd_value}" if cd_value is not None else "每場一次"
                ability_line = (
                    f"\n技能：[{phase_text}({cd_text})] {ability['name']}\n"
                    f"{ability.get('description', '')}"
                )
            else:
                ability_line = "\n技能：無"
            embed.add_field(
                name=character["name"],
                value=f"生命 {character['hp']}｜攻擊 {character['atk']}｜防禦 {character['defense']}｜敏捷 {character['agi']}{ability_line}",
                inline=False,
            )
        view = JuiceBattlePlayerView(cog=self, userid=userid)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="juice_battle_bag", description="查看 Juice Battle 裝備背包")
    async def juice_battle_bag(self, interaction: discord.Interaction):
        """
        開啟裝備背包（分頁、裝備、丟棄）。

        Args:
            interaction (discord.Interaction): "slash 互動"
        """
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            user_data = await self.load_user(userid)
            juice_battle = user_data["juice_battle"]
            if juice_battle.get("playing"):
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle",
                        description=self.playing_block_description(juice_battle),
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
                return
            await common.mongo_storage.replace_user(userid, user_data)
            embed = self.build_bag_embed(juice_battle, 0)
            view = JuiceBattleBagView(cog=self, userid=userid, page=0)
            await view.attach_slot_buttons(juice_battle)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="juice_battle", description="發起 Juice Battle 對戰")
    @app_commands.describe(opponent="要挑戰的玩家，或 Natalie")
    @app_commands.rename(opponent="對手")
    async def juice_battle(self, interaction: discord.Interaction, opponent: discord.Member):
        """
        挑戰玩家或 Natalie，開啟對戰／同意挑戰流程。

        Args:
            interaction (discord.Interaction): "slash 互動"
            opponent (discord.Member): "對手成員"
        """
        challenger = interaction.user
        challenger_id = str(challenger.id)
        opponent_id = str(opponent.id)

        # 檢查對手合法性
        if opponent_id == challenger_id:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="不能挑戰自己。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        if opponent.bot and opponent.id != common.bot_id:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="只能挑戰玩家或 Natalie。", color=common.bot_error_color),
                ephemeral=True,
            )
            return

        async with common.jsonio_lock:
            challenger_data = await self.load_user(challenger_id)
            challenger_juice = challenger_data["juice_battle"]
            if challenger_juice.get("playing"):
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle",
                        description=self.playing_block_description(challenger_juice),
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
                return

            # 挑戰 Natalie：直接開戰
            if opponent.id == common.bot_id:
                fighter_player = self.build_fighter(
                    user_id=challenger_id,
                    display_name=challenger.display_name,
                    character_id=challenger_juice["character_id"],
                    juice_battle=challenger_juice,
                    is_bot=False,
                )
                fighter_bot = self.build_bot_fighter()
                await common.mongo_storage.replace_user(challenger_id, challenger_data)

                first, second, initiative_text = self.resolve_initiative(fighter_player, fighter_bot)
                view = JuiceBattleView(
                    cog=self,
                    fighter_a=fighter_player,
                    fighter_b=fighter_bot,
                    attacker_id=first["user_id"],
                    defender_id=second["user_id"],
                    phase="attack",
                    log_text=initiative_text,
                    vs_bot=True,
                )
                embed = self.build_battle_embed(view)
                await interaction.response.send_message(embed=embed, view=view)
                message = await interaction.original_response()
                view.message = message
                session = {
                    "opponent_id": str(common.bot_id),
                    "guild_id": str(interaction.guild_id) if interaction.guild_id else "@me",
                    "channel_id": str(message.channel.id),
                    "message_id": str(message.id),
                    "vs_bot": True,
                }
                async with common.jsonio_lock:
                    await self.set_playing_session(challenger_id, session)
                await view.start_after_initiative(None)
                return

            # 挑戰玩家：檢查對手是否忙碌，送出同意挑戰
            opponent_data = await self.load_user(opponent_id)
            opponent_juice = opponent_data["juice_battle"]
            if opponent_juice.get("playing"):
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle",
                        description=f"{opponent.display_name} 正在對戰中。",
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
                return
            await common.mongo_storage.replace_user(challenger_id, challenger_data)
            await common.mongo_storage.replace_user(opponent_id, opponent_data)

            embed = Embed(
                title="Juice Battle｜挑戰",
                description=(
                    f"{challenger.mention} 向 {opponent.mention} 發起挑戰！\n"
                    f"賭注：{self.default_bet} {common.cake_emoji}\n"
                    f"請 {opponent.mention} 按下「同意挑戰」開始。"
                ),
                color=common.bot_color,
            )
            embed.add_field(
                name=f"{challenger.display_name} 的素質",
                value=self.format_stat_block(challenger_juice["character_id"], challenger_juice),
                inline=False,
            )
            view = JuiceBattleChallengeView(
                cog=self,
                challenger_id=challenger_id,
                opponent_id=opponent_id,
                challenger_name=challenger.display_name,
                opponent_name=opponent.display_name,
            )
            await interaction.response.send_message(embed=embed, view=view)
            message = await interaction.original_response()
            view.message = message
            jump_url = message.jump_url
            await self.notify_challenge_dm(opponent, challenger, jump_url)

    @app_commands.command(name="juice_battle_leaderboard", description="Juice Battle 各角色勝率排行榜")
    async def juice_battle_leaderboard(self, interaction: discord.Interaction):
        """
        顯示每個角色勝率前三名，以及自己各角色的勝率與場數。

        Args:
            interaction (discord.Interaction): "slash 互動"
        """
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            user_data = await self.load_user(userid)
            my_stats = dict(user_data["juice_battle"].get("character_stats") or {})
            await common.mongo_storage.replace_user(userid, user_data)

            # 收集所有玩家的角色統計
            collection = common.mongo_storage.get_collection("userdata")
            per_character_players = {character_id: [] for character_id in self.characters}
            if collection is not None:
                async for document in collection.find(
                    {"juice_battle.character_stats": {"$exists": True}},
                    {"_id": 1, "juice_battle.character_stats": 1},
                ):
                    document_id = document.get("_id")
                    if not isinstance(document_id, str) or not document_id.isdigit():
                        continue
                    stats_map = (document.get("juice_battle") or {}).get("character_stats") or {}
                    if not isinstance(stats_map, dict):
                        continue
                    for character_id, entry in stats_map.items():
                        if character_id not in self.characters or not isinstance(entry, dict):
                            continue
                        round_count = int(entry.get("round", 0))
                        win_count = int(entry.get("win", 0))
                        if round_count < self.leaderboard_min_rounds:
                            continue
                        per_character_players[character_id].append(
                            {
                                "user_id": document_id,
                                "win": win_count,
                                "round": round_count,
                                "win_rate": win_count / round_count,
                            }
                        )

        embed = Embed(
            title="Juice Battle｜勝率排行榜",
            description=f"各角色勝率前 {self.leaderboard_top_n} 名（至少 {self.leaderboard_min_rounds} 場）。",
            color=common.bot_color,
        )

        # 每個角色的前三名
        for character_id, character in self.characters.items():
            players = per_character_players.get(character_id) or []
            players.sort(key=lambda item: (item["win_rate"], item["round"]), reverse=True)
            top_players = players[: self.leaderboard_top_n]
            if not top_players:
                embed.add_field(name=character["name"], value="尚無紀錄", inline=False)
                continue
            lines = []
            for index, player in enumerate(top_players):
                member = interaction.guild.get_member(int(player["user_id"])) if interaction.guild else None
                user_object = member or self.bot.get_user(int(player["user_id"]))
                display_name = user_object.display_name if user_object else player["user_id"]
                lines.append(
                    f"{index + 1}. {display_name} 勝率:**{player['win_rate']:.1%}** 場數:**{player['round']}**"
                )
            embed.add_field(name=character["name"], value="\n".join(lines), inline=False)

        # 自己各角色勝率
        my_lines = []
        for character_id, character in self.characters.items():
            entry = my_stats.get(character_id)
            if not isinstance(entry, dict):
                continue
            round_count = int(entry.get("round", 0))
            if round_count <= 0:
                continue
            win_count = int(entry.get("win", 0))
            my_lines.append(
                f"**{character['name']}** 勝率:**{self.format_win_rate(win_count, round_count)}** 場數:**{round_count}**"
            )
        if my_lines:
            embed.add_field(name="你的各角色戰績", value="\n".join(my_lines), inline=False)
        else:
            embed.add_field(name="你的各角色戰績", value="尚無遊玩紀錄", inline=False)

        await interaction.response.send_message(embed=embed)


class JuiceBattleCharacterSelect(discord.ui.Select):
    """角色選擇下拉選單。"""

    def __init__(self, cog: JuiceBattle):
        options = [
            discord.SelectOption(
                label=character["name"],
                value=character_id,
                description=f"HP{character['hp']} ATK{character['atk']} DEF{character['defense']} AGI{character['agi']}",
            )
            for character_id, character in cog.characters.items()
        ]
        super().__init__(placeholder="選擇角色", options=options)

    async def callback(self, interaction: discord.Interaction):
        """
        寫入選擇的角色。

        Args:
            interaction (discord.Interaction): "Select 互動"
        """
        view: JuiceBattlePlayerView = self.view  # type: ignore[assignment]
        character_id = self.values[0]
        async with common.jsonio_lock:
            user_data = await view.cog.load_user(view.userid)
            juice_battle = user_data["juice_battle"]
            if juice_battle.get("playing"):
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle",
                        description=view.cog.playing_block_description(juice_battle),
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
                return
            juice_battle["character_id"] = character_id
            await common.mongo_storage.replace_user(view.userid, user_data)
        name = view.cog.characters[character_id]["name"]
        for child in view.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=Embed(title="Juice Battle｜更換角色", description=f"已更換為 **{name}**。", color=common.bot_color),
            view=view,
        )
        view.stop()


class JuiceBattlePlayerView(discord.ui.View):
    """角色選擇介面。"""

    def __init__(self, *, cog: JuiceBattle, userid: str):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.userid = userid
        self.add_item(JuiceBattleCharacterSelect(cog))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        只允許本人操作。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "True"
        """
        if str(interaction.user.id) == self.userid:
            return True
        await interaction.response.send_message(
            embed=Embed(title="Juice Battle", description="這不是你的角色選擇。", color=common.bot_error_color),
            ephemeral=True,
        )
        return False


class JuiceBattleBagEquipButton(discord.ui.Button):
    """裝備指定背包格。"""

    def __init__(self, *, slot_index: int, row: int):
        super().__init__(label=f"裝備{slot_index + 1}", style=discord.ButtonStyle.primary, row=row)
        self.slot_index = slot_index

    async def callback(self, interaction: discord.Interaction):
        """
        處理裝備按鈕。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleBagView = self.view  # type: ignore[assignment]
        await view.on_equip(interaction, self.slot_index)


class JuiceBattleBagDiscardButton(discord.ui.Button):
    """丟棄指定背包格（進入確認）。"""

    def __init__(self, *, slot_index: int, row: int):
        super().__init__(label=f"丟棄{slot_index + 1}", style=discord.ButtonStyle.danger, row=row)
        self.slot_index = slot_index

    async def callback(self, interaction: discord.Interaction):
        """
        處理丟棄按鈕。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleBagView = self.view  # type: ignore[assignment]
        await view.on_discard(interaction, self.slot_index)


class JuiceBattleBagPrevButton(discord.ui.Button):
    """背包上一頁。"""

    def __init__(self, *, disabled: bool):
        super().__init__(label="上一頁", style=discord.ButtonStyle.secondary, row=4, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        """
        切到上一頁。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleBagView = self.view  # type: ignore[assignment]
        await view.on_prev(interaction)


class JuiceBattleBagNextButton(discord.ui.Button):
    """背包下一頁。"""

    def __init__(self, *, disabled: bool):
        super().__init__(label="下一頁", style=discord.ButtonStyle.secondary, row=4, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        """
        切到下一頁。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleBagView = self.view  # type: ignore[assignment]
        await view.on_next(interaction)


class JuiceBattleBagConfirmDiscardButton(discord.ui.Button):
    """確認丟棄。"""

    def __init__(self):
        super().__init__(label="確認丟棄", style=discord.ButtonStyle.danger, row=0)

    async def callback(self, interaction: discord.Interaction):
        """
        確認丟棄。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleBagView = self.view  # type: ignore[assignment]
        await view.on_confirm_discard(interaction)


class JuiceBattleBagCancelDiscardButton(discord.ui.Button):
    """取消丟棄。"""

    def __init__(self):
        super().__init__(label="取消", style=discord.ButtonStyle.secondary, row=0)

    async def callback(self, interaction: discord.Interaction):
        """
        取消丟棄確認。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleBagView = self.view  # type: ignore[assignment]
        await view.on_cancel_discard(interaction)


class JuiceBattleBagView(discord.ui.View):
    """裝備背包：分頁、裝備、丟棄確認。"""

    def __init__(self, *, cog: JuiceBattle, userid: str, page: int, discard_confirm_slot: int | None = None):
        super().__init__(timeout=cog.bag_view_timeout)
        self.cog = cog
        self.userid = userid
        self.page = page
        self.discard_confirm_slot = discard_confirm_slot
        self.max_page = (cog.bag_size - 1) // cog.bag_page_size
        self.page_start = page * cog.bag_page_size
        self.page_end = min(self.page_start + cog.bag_page_size, cog.bag_size)
        self.rebuild_items()

    def rebuild_items(self):
        """
        依目前頁面與丟棄確認狀態重建按鈕。
        """
        self.clear_items()
        if self.discard_confirm_slot is not None:
            self.add_item(JuiceBattleBagConfirmDiscardButton())
            self.add_item(JuiceBattleBagCancelDiscardButton())
            return
        self.add_item(JuiceBattleBagPrevButton(disabled=self.page <= 0))
        self.add_item(JuiceBattleBagNextButton(disabled=self.page >= self.max_page))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        只允許本人操作背包。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "True"
        """
        if str(interaction.user.id) == self.userid:
            return True
        await interaction.response.send_message(
            embed=Embed(title="Juice Battle", description="這不是你的裝備背包。", color=common.bot_error_color),
            ephemeral=True,
        )
        return False

    async def attach_slot_buttons(self, juice_battle: dict):
        """
        依背包內容為目前頁加上裝備／丟棄按鈕。

        Args:
            juice_battle (dict): "{'bag': []}"
        """
        page_buttons = [
            child
            for child in self.children
            if isinstance(child, (JuiceBattleBagPrevButton, JuiceBattleBagNextButton))
        ]
        self.clear_items()
        bag = juice_battle["bag"]
        equip_count = 0
        discard_count = 0
        for index in range(self.page_start, self.page_end):
            entry = bag[index]
            if not isinstance(entry, dict):
                continue
            self.add_item(JuiceBattleBagEquipButton(slot_index=index, row=equip_count // 5))
            self.add_item(JuiceBattleBagDiscardButton(slot_index=index, row=2 + discard_count // 5))
            equip_count += 1
            discard_count += 1
        for button in page_buttons:
            self.add_item(button)

    async def refresh_message(self, interaction: discord.Interaction, juice_battle: dict):
        """
        用目前狀態更新背包訊息。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            juice_battle (dict): "{'bag': []}"
        """
        new_view = JuiceBattleBagView(
            cog=self.cog,
            userid=self.userid,
            page=self.page,
            discard_confirm_slot=self.discard_confirm_slot,
        )
        if new_view.discard_confirm_slot is None:
            await new_view.attach_slot_buttons(juice_battle)
        embed = self.cog.build_bag_embed(juice_battle, self.page, self.discard_confirm_slot)
        await interaction.response.edit_message(embed=embed, view=new_view)
        self.stop()

    async def on_prev(self, interaction: discord.Interaction):
        """
        上一頁。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        async with common.jsonio_lock:
            user_data = await self.cog.load_user(self.userid)
            juice_battle = user_data["juice_battle"]
        self.page = max(0, self.page - 1)
        self.discard_confirm_slot = None
        self.page_start = self.page * self.cog.bag_page_size
        self.page_end = min(self.page_start + self.cog.bag_page_size, self.cog.bag_size)
        await self.refresh_message(interaction, juice_battle)

    async def on_next(self, interaction: discord.Interaction):
        """
        下一頁。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        async with common.jsonio_lock:
            user_data = await self.cog.load_user(self.userid)
            juice_battle = user_data["juice_battle"]
        self.page = min(self.max_page, self.page + 1)
        self.discard_confirm_slot = None
        self.page_start = self.page * self.cog.bag_page_size
        self.page_end = min(self.page_start + self.cog.bag_page_size, self.cog.bag_size)
        await self.refresh_message(interaction, juice_battle)

    async def on_equip(self, interaction: discord.Interaction, slot_index: int):
        """
        裝備指定格子的武器或防具。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            slot_index (int): "0"
        """
        async with common.jsonio_lock:
            user_data = await self.cog.load_user(self.userid)
            juice_battle = user_data["juice_battle"]
            if juice_battle.get("playing"):
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle",
                        description=self.cog.playing_block_description(juice_battle),
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
                return
            entry = juice_battle["bag"][slot_index] if slot_index < len(juice_battle["bag"]) else None
            if not isinstance(entry, dict):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="該格是空的。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            if entry.get("kind") == "weapon":
                juice_battle["equipped_weapon_slot"] = slot_index
            elif entry.get("kind") == "armor":
                juice_battle["equipped_armor_slot"] = slot_index
            else:
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="無法裝備此物品。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            await common.mongo_storage.replace_user(self.userid, user_data)
        self.discard_confirm_slot = None
        await self.refresh_message(interaction, juice_battle)

    async def on_discard(self, interaction: discord.Interaction, slot_index: int):
        """
        進入丟棄確認。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            slot_index (int): "2"
        """
        async with common.jsonio_lock:
            user_data = await self.cog.load_user(self.userid)
            juice_battle = user_data["juice_battle"]
            entry = juice_battle["bag"][slot_index] if slot_index < len(juice_battle["bag"]) else None
            if not isinstance(entry, dict):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="該格是空的。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            template = self.cog.item_template(entry.get("kind"), entry.get("item_id"))
            if template is not None and template.get("starter"):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="初始武器／防具不可丟棄。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
        self.discard_confirm_slot = slot_index
        await self.refresh_message(interaction, juice_battle)

    async def on_confirm_discard(self, interaction: discord.Interaction):
        """
        確認丟棄目前選定格子。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        slot_index = self.discard_confirm_slot
        if slot_index is None:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="沒有待丟棄的物品。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        async with common.jsonio_lock:
            user_data = await self.cog.load_user(self.userid)
            juice_battle = user_data["juice_battle"]
            entry = juice_battle["bag"][slot_index] if slot_index < len(juice_battle["bag"]) else None
            if not isinstance(entry, dict):
                self.discard_confirm_slot = None
                await self.refresh_message(interaction, juice_battle)
                return
            template = self.cog.item_template(entry.get("kind"), entry.get("item_id"))
            if template is not None and template.get("starter"):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="初始武器／防具不可丟棄。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            juice_battle["bag"][slot_index] = None
            if juice_battle.get("equipped_weapon_slot") == slot_index:
                juice_battle["equipped_weapon_slot"] = None
            if juice_battle.get("equipped_armor_slot") == slot_index:
                juice_battle["equipped_armor_slot"] = None
            await common.mongo_storage.replace_user(self.userid, user_data)
        self.discard_confirm_slot = None
        await self.refresh_message(interaction, juice_battle)

    async def on_cancel_discard(self, interaction: discord.Interaction):
        """
        取消丟棄確認。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        async with common.jsonio_lock:
            user_data = await self.cog.load_user(self.userid)
            juice_battle = user_data["juice_battle"]
        self.discard_confirm_slot = None
        await self.refresh_message(interaction, juice_battle)


class JuiceBattleChallengeView(discord.ui.View):
    """PvP 同意挑戰。"""

    def __init__(self, *, cog: JuiceBattle, challenger_id: str, opponent_id: str, challenger_name: str, opponent_name: str):
        super().__init__(timeout=cog.challenge_timeout)
        self.cog = cog
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.challenger_name = challenger_name
        self.opponent_name = opponent_name
        self.message: discord.Message | None = None
        self.accepted = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        僅被挑戰者可按同意。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "True"
        """
        if str(interaction.user.id) == self.opponent_id:
            return True
        await interaction.response.send_message(
            embed=Embed(title="Juice Battle", description="只有被挑戰者可以同意。", color=common.bot_error_color),
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="同意挑戰", style=discord.ButtonStyle.danger)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        同意挑戰並開始戰鬥。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            button (discord.ui.Button): "同意挑戰"
        """
        if self.accepted:
            return
        async with common.jsonio_lock:
            challenger_data = await self.cog.load_user(self.challenger_id)
            opponent_data = await self.cog.load_user(self.opponent_id)
            if challenger_data["juice_battle"].get("playing") or opponent_data["juice_battle"].get("playing"):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="其中一方已在對戰中，無法開始。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            fighter_a = self.cog.build_fighter(
                user_id=self.challenger_id,
                display_name=self.challenger_name,
                character_id=challenger_data["juice_battle"]["character_id"],
                juice_battle=challenger_data["juice_battle"],
                is_bot=False,
            )
            fighter_b = self.cog.build_fighter(
                user_id=self.opponent_id,
                display_name=self.opponent_name,
                character_id=opponent_data["juice_battle"]["character_id"],
                juice_battle=opponent_data["juice_battle"],
                is_bot=False,
            )
            self.accepted = True
            button.disabled = True

        first, second, initiative_text = self.cog.resolve_initiative(fighter_a, fighter_b)
        battle_view = JuiceBattleView(
            cog=self.cog,
            fighter_a=fighter_a,
            fighter_b=fighter_b,
            attacker_id=first["user_id"],
            defender_id=second["user_id"],
            phase="attack",
            log_text=initiative_text,
            vs_bot=False,
        )
        embed = self.cog.build_battle_embed(battle_view)
        await interaction.response.edit_message(embed=embed, view=battle_view)
        message = interaction.message
        battle_view.message = message
        base_session = {
            "guild_id": str(interaction.guild_id) if interaction.guild_id else "@me",
            "channel_id": str(message.channel.id),
            "message_id": str(message.id),
            "vs_bot": False,
        }
        challenger_session = dict(base_session)
        challenger_session["opponent_id"] = self.opponent_id
        opponent_session = dict(base_session)
        opponent_session["opponent_id"] = self.challenger_id
        async with common.jsonio_lock:
            await self.cog.set_playing_session(self.challenger_id, challenger_session)
            await self.cog.set_playing_session(self.opponent_id, opponent_session)
        await battle_view.start_after_initiative(None)
        self.stop()

    async def on_timeout(self) -> None:
        """
        挑戰逾時，取消按鈕。
        """
        if self.accepted:
            return
        for child in self.children:
            child.disabled = True
        if self.message is None:
            return
        embed = Embed(
            title="Juice Battle｜挑戰",
            description=f"{self.challenger_name} 對 {self.opponent_name} 的挑戰已逾時取消。",
            color=common.bot_error_color,
        )
        try:
            await self.message.edit(embed=embed, view=self)
        except Exception:
            pass


class JuiceBattleAttackButton(discord.ui.Button):
    """攻擊按鈕。"""

    def __init__(self):
        super().__init__(label="攻擊", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        """
        處理攻擊。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleView = self.view  # type: ignore[assignment]
        await view.on_attack(interaction)


class JuiceBattleDefendButton(discord.ui.Button):
    """防禦按鈕。"""

    def __init__(self):
        super().__init__(label="防禦", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        """
        處理防禦。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleView = self.view  # type: ignore[assignment]
        await view.on_defend(interaction)


class JuiceBattleDodgeButton(discord.ui.Button):
    """閃避按鈕。"""

    def __init__(self):
        super().__init__(label="閃避", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        """
        處理閃避。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleView = self.view  # type: ignore[assignment]
        await view.on_dodge(interaction)


class JuiceBattleSkillButton(discord.ui.Button):
    """角色技能按鈕（綠色，與攻擊／防禦／閃避區隔）。"""

    def __init__(self, *, label: str, armed: bool):
        display = f"{label}（已發動）" if armed else label
        super().__init__(label=display, style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        """
        發動或取消發動技能。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleView = self.view  # type: ignore[assignment]
        await view.on_skill(interaction)


class JuiceBattleView(discord.ui.View):
    """回合制戰鬥主介面。"""

    def __init__(
        self,
        *,
        cog: JuiceBattle,
        fighter_a: dict,
        fighter_b: dict,
        attacker_id: str,
        defender_id: str,
        phase: str,
        log_text: str,
        vs_bot: bool,
        pending_attack_total: int | None = None,
        pending_attack_dice: int | None = None,
        pending_bind: bool = False,
        pending_poison: bool = False,
        result_text: str | None = None,
    ):
        super().__init__(timeout=cog.battle_timeout)
        self.cog = cog
        self.fighter_a = fighter_a
        self.fighter_b = fighter_b
        self.attacker_id = attacker_id
        self.defender_id = defender_id
        self.phase = phase
        self.log_text = log_text
        self.vs_bot = vs_bot
        self.pending_attack_total = pending_attack_total
        self.pending_attack_dice = pending_attack_dice
        self.pending_bind = pending_bind
        self.pending_poison = pending_poison
        self.result_text = result_text
        self.message: discord.Message | None = None
        self.finished = phase == "ended"
        self.rebuild_buttons()

    def fighter_by_id(self, user_id: str) -> dict:
        """
        依 user_id 取得戰鬥方。

        Args:
            user_id (str): "4108"

        Returns:
            fighter (dict): "{'hp': 10}"
        """
        if self.fighter_a["user_id"] == str(user_id):
            return self.fighter_a
        return self.fighter_b

    def other_fighter(self, user_id: str) -> dict:
        """
        取得另一方。

        Args:
            user_id (str): "4108"

        Returns:
            fighter (dict): "{'hp': 10}"
        """
        if self.fighter_a["user_id"] == str(user_id):
            return self.fighter_b
        return self.fighter_a

    def append_log(self, line: str):
        """
        串接戰鬥紀錄。

        Args:
            line (str): "中毒傷害"
        """
        if self.log_text:
            self.log_text = f"{self.log_text}\n{line}"
        else:
            self.log_text = line

    def prepare_attack_phase(self) -> bool:
        """
        進入攻擊階段：攻擊技能 CD-1、中毒跳傷。若中毒致死回傳 True。

        Returns:
            died (bool): "True 表示攻擊方已因中毒死亡"
        """
        attacker = self.fighter_by_id(self.attacker_id)
        ability = self.cog.character_ability(attacker["character_id"])
        if ability and ability.get("phase") == "attack" and int(attacker.get("skill_cd", 0)) > 0:
            attacker["skill_cd"] = int(attacker["skill_cd"]) - 1
        attacker["skill_armed"] = False

        # 中毒：攻擊階段開始時 -1HP
        if int(attacker.get("poison_remaining", 0)) > 0:
            attacker["hp"] = max(0, attacker["hp"] - 1)
            attacker["poison_remaining"] = int(attacker["poison_remaining"]) - 1
            self.append_log(
                f"{attacker['display_name']} 中毒，受到 **1** 點傷害"
                f"（剩餘 {attacker['poison_remaining']} 回合）"
            )
            if attacker["hp"] <= 0:
                return True
        return False

    def prepare_defend_phase(self):
        """
        進入防守階段：防守技能 CD-1。
        """
        defender = self.fighter_by_id(self.defender_id)
        ability = self.cog.character_ability(defender["character_id"])
        if ability and ability.get("phase") == "defend" and int(defender.get("skill_cd", 0)) > 0:
            defender["skill_cd"] = int(defender["skill_cd"]) - 1
        defender["skill_armed"] = False

    def rebuild_buttons(self):
        """
        依階段重建攻擊／防禦／閃避／技能按鈕。
        """
        self.clear_items()
        if self.phase == "ended" or self.finished:
            return
        if self.phase == "attack":
            attacker = self.fighter_by_id(self.attacker_id)
            if attacker.get("is_bot"):
                return
            self.add_item(JuiceBattleAttackButton())
            ability = self.cog.character_ability(attacker["character_id"])
            if ability and ability.get("phase") == "attack":
                if attacker.get("skill_armed") or self.cog.skill_is_ready(attacker, "attack"):
                    self.add_item(JuiceBattleSkillButton(label=ability["name"], armed=bool(attacker.get("skill_armed"))))
            return
        if self.phase == "defend":
            defender = self.fighter_by_id(self.defender_id)
            if defender.get("is_bot"):
                return
            self.add_item(JuiceBattleDefendButton())
            if not self.pending_bind:
                self.add_item(JuiceBattleDodgeButton())
            ability = self.cog.character_ability(defender["character_id"])
            if ability and ability.get("phase") == "defend":
                if defender.get("skill_armed") or self.cog.skill_is_ready(defender, "defend"):
                    self.add_item(JuiceBattleSkillButton(label=ability["name"], armed=bool(defender.get("skill_armed"))))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        僅允許當前應行動的玩家操作。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "True"
        """
        if self.finished or self.phase == "ended":
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="此戰鬥已結束或已失效。", color=common.bot_error_color),
                ephemeral=True,
            )
            return False
        actor_id = self.attacker_id if self.phase == "attack" else self.defender_id
        if str(interaction.user.id) != str(actor_id):
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="現在不是你的回合。", color=common.bot_error_color),
                ephemeral=True,
            )
            return False
        return True

    async def replace_with_fresh_view(self, interaction: discord.Interaction | None) -> "JuiceBattleView":
        """
        以新 View 延續狀態（重設 timeout）。

        Args:
            interaction (discord.Interaction | None): "按鈕互動或 None"

        Returns:
            new_view (JuiceBattleView): "新的戰鬥 View"
        """
        new_view = JuiceBattleView(
            cog=self.cog,
            fighter_a=self.fighter_a,
            fighter_b=self.fighter_b,
            attacker_id=self.attacker_id,
            defender_id=self.defender_id,
            phase=self.phase,
            log_text=self.log_text,
            vs_bot=self.vs_bot,
            pending_attack_total=self.pending_attack_total,
            pending_attack_dice=self.pending_attack_dice,
            pending_bind=self.pending_bind,
            pending_poison=self.pending_poison,
            result_text=self.result_text,
        )
        new_view.message = self.message
        embed = self.cog.build_battle_embed(new_view)
        if interaction is not None:
            await interaction.response.edit_message(embed=embed, view=new_view)
        elif self.message is not None:
            await self.message.edit(embed=embed, view=new_view)
        self.stop()
        return new_view

    async def finish_battle(self, *, winner: dict | None, reason: str, interaction: discord.Interaction | None):
        """
        結束戰鬥並清除雙方 playing。

        Args:
            winner (dict | None): "{'display_name': 'Ani'}"
            reason (str): "逾時判負"
            interaction (discord.Interaction | None): "按鈕互動或 None"
        """
        self.phase = "ended"
        self.finished = True
        if winner is None:
            self.result_text = reason
        else:
            self.result_text = f"**{winner['display_name']}** 獲勝！\n{reason}"
        self.rebuild_buttons()
        embed = self.cog.build_battle_embed(self)
        if interaction is not None and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=None)
        elif self.message is not None:
            await self.message.edit(embed=embed, view=None)
        async with common.jsonio_lock:
            if winner is not None:
                loser = self.other_fighter(winner["user_id"])
                await self.cog.record_battle_outcome(winner, loser)
            await self.cog.clear_session(self.fighter_a["user_id"])
            if not self.fighter_b.get("is_bot"):
                await self.cog.clear_session(self.fighter_b["user_id"])
        self.stop()

    async def on_skill(self, interaction: discord.Interaction):
        """
        發動或取消發動當前階段技能。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        actor = self.fighter_by_id(self.attacker_id if self.phase == "attack" else self.defender_id)
        ability = self.cog.character_ability(actor["character_id"])
        if ability is None or ability.get("phase") != self.phase:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="此階段無法使用技能。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        if actor.get("skill_armed"):
            actor["skill_armed"] = False
        else:
            if not self.cog.skill_is_ready(actor, self.phase):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="技能尚未準備好。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            actor["skill_armed"] = True
        await self.replace_with_fresh_view(interaction)

    async def on_attack(self, interaction: discord.Interaction):
        """
        攻擊方按下攻擊。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        await self.execute_attack(interaction)

    async def execute_attack(self, interaction: discord.Interaction | None):
        """
        執行攻擊擲骰並進入防守階段。

        Args:
            interaction (discord.Interaction | None): "按鈕互動或 None"
        """
        attacker = self.fighter_by_id(self.attacker_id)
        ability = self.cog.consume_armed_skill(attacker)
        self.pending_bind = False
        self.pending_poison = False
        skill_note = ""
        if ability is not None:
            skill_note = f"（發動 {ability['name']}）"
            if ability["id"] == "bind":
                self.pending_bind = True
            elif ability["id"] == "poison":
                self.pending_poison = True

        # 擲攻擊骰（架式對調時用防禦值）
        atk_base, atk_offset = self.cog.attack_roll_stats(attacker)
        _dice, total = self.cog.roll_stat(atk_base, atk_offset)
        if attacker.get("stance_swap_attack"):
            attacker["stance_swap_attack"] = False
            skill_note = f"{skill_note}（架式對調攻擊）" if skill_note else "（架式對調攻擊）"
        self.pending_attack_dice = _dice
        self.pending_attack_total = total
        attack_line = f"{attacker['display_name']} 攻擊 **{total}**{skill_note}"
        if interaction is None and self.log_text:
            self.append_log(attack_line)
        else:
            self.log_text = attack_line
        self.phase = "defend"
        self.prepare_defend_phase()
        defender = self.fighter_by_id(self.defender_id)

        # 對戰機器人：防守方立刻決策並結算
        if defender.get("is_bot"):
            await self.resolve_bot_defense(interaction)
            return

        await self.replace_with_fresh_view(interaction)

    async def resolve_bot_defense(self, interaction: discord.Interaction | None):
        """
        Natalie 依技能／HP／預期傷害選擇防禦或閃避並結算。

        Args:
            interaction (discord.Interaction | None): "按鈕互動或 None"
        """
        defender = self.fighter_by_id(self.defender_id)
        attack_total = self.pending_attack_total or 0

        # 自動發動可用的防守技能（冰箱僅在可能致死時發動）
        if self.cog.skill_is_ready(defender, "defend"):
            ability = self.cog.character_ability(defender["character_id"])
            if ability and ability["id"] == "fridge":
                if attack_total >= defender["hp"]:
                    defender["skill_armed"] = True
            else:
                defender["skill_armed"] = True

        stance_swap_defend = bool(
            defender.get("skill_armed")
            and (self.cog.character_ability(defender["character_id"]) or {}).get("id") == "stance_swap"
        )
        fridge_armed = bool(
            defender.get("skill_armed")
            and (self.cog.character_ability(defender["character_id"]) or {}).get("id") == "fridge"
        )

        # 被束縛只能防禦；發動冰箱則選閃避（失敗吃滿傷以觸發回血）
        if self.pending_bind:
            mode = "defend"
        elif fridge_armed:
            mode = "dodge"
        elif defender["hp"] == 1:
            mode = "dodge"
        else:
            defense_base, defense_offset = self.cog.defense_roll_stats(defender, stance_swap_defend=stance_swap_defend)
            defend_damage_sum = 0
            for dice in range(1, 7):
                defense_total = dice + defense_base + defense_offset
                defend_damage_sum += max(1, attack_total - defense_total)
            defend_expected = defend_damage_sum / 6

            agility_base = defender["agi"] + defender["agi_offset"]
            dodge_damage_sum = 0
            for dice in range(1, 7):
                dodge_total = dice + agility_base
                if attack_total >= dodge_total:
                    dodge_damage_sum += attack_total
            dodge_expected = dodge_damage_sum / 6

            if defend_expected < dodge_expected:
                mode = "defend"
            elif dodge_expected < defend_expected:
                mode = "dodge"
            else:
                mode = random.choice(["defend", "dodge"])

        await self.apply_defense_choice(interaction, mode=mode, respond=True)

    async def on_defend(self, interaction: discord.Interaction):
        """
        防守方選擇防禦。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        await self.apply_defense_choice(interaction, mode="defend", respond=True)

    async def on_dodge(self, interaction: discord.Interaction):
        """
        防守方選擇閃避。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        if self.pending_bind:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="你被束縛，無法閃避。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        await self.apply_defense_choice(interaction, mode="dodge", respond=True)

    async def apply_defense_choice(self, interaction: discord.Interaction | None, *, mode: str, respond: bool):
        """
        結算防禦或閃避傷害，並處理攻守互換／結束／bot 連段。

        Args:
            interaction (discord.Interaction | None): "按鈕互動或 None"
            mode (str): "defend"
            respond (bool): "True"
        """
        attacker = self.fighter_by_id(self.attacker_id)
        defender = self.fighter_by_id(self.defender_id)
        attack_total = self.pending_attack_total or 0
        ability = self.cog.consume_armed_skill(defender)
        stance_swap_defend = ability is not None and ability["id"] == "stance_swap"
        fridge_armed = ability is not None and ability["id"] == "fridge"
        skill_note = f"（發動 {ability['name']}）" if ability else ""

        # 計算傷害
        attack_line = f"{attacker['display_name']} 攻擊 **{attack_total}**"
        if mode == "defend":
            def_base, def_offset = self.cog.defense_roll_stats(defender, stance_swap_defend=stance_swap_defend)
            _dice, defense_total = self.cog.roll_stat(def_base, def_offset)
            damage = max(1, attack_total - defense_total)
            outcome_line = f"{defender['display_name']} 防禦 **{defense_total}**{skill_note}"
        else:
            _dice, dodge_total = self.cog.roll_stat(defender["agi"], defender["agi_offset"])
            if attack_total >= dodge_total:
                damage = attack_total
                outcome_line = f"{defender['display_name']} 閃避 **{dodge_total}**{skill_note}，失敗"
            else:
                damage = 0
                outcome_line = f"{defender['display_name']} 閃避 **{dodge_total}**{skill_note}，成功，無傷！"

        # 冰箱：致死傷害改為回復
        if fridge_armed and damage > 0 and defender["hp"] - damage <= 0:
            heal = damage
            defender["hp"] = min(defender["max_hp"], defender["hp"] + heal)
            self.log_text = (
                f"{attack_line}\n{outcome_line}\n"
                f"{defender['display_name']} 冰箱發動！傷害無效，回復 **{heal}** 點生命"
            )
            damage = 0
        else:
            defender["hp"] = max(0, defender["hp"] - damage)
            if mode == "defend" or damage > 0:
                self.log_text = f"{attack_line}\n{outcome_line}，受到 **{damage}** 點傷害"
            else:
                self.log_text = f"{attack_line}\n{outcome_line}"

        # 調整架式：接著自己的攻擊也對調
        if stance_swap_defend:
            defender["stance_swap_attack"] = True

        # 中毒：攻擊成功（傷害 > 0）上毒
        if self.pending_poison and damage > 0:
            defender["poison_remaining"] = 3
            self.append_log(f"{defender['display_name']} 中毒（持續 3 回合）")

        self.pending_attack_total = None
        self.pending_attack_dice = None
        self.pending_bind = False
        self.pending_poison = False

        # 檢查勝負
        if defender["hp"] <= 0:
            await self.finish_battle(winner=attacker, reason="對手生命歸零。", interaction=interaction if respond else None)
            return

        # 攻守互換並準備下一攻擊階段
        self.attacker_id, self.defender_id = self.defender_id, self.attacker_id
        self.phase = "attack"
        if self.prepare_attack_phase():
            dead = self.fighter_by_id(self.attacker_id)
            winner = self.other_fighter(dead["user_id"])
            await self.finish_battle(winner=winner, reason="中毒致死。", interaction=interaction if respond else None)
            return

        next_attacker = self.fighter_by_id(self.attacker_id)
        if next_attacker.get("is_bot"):
            if respond and interaction is not None and not interaction.response.is_done():
                new_view = await self.replace_with_fresh_view(interaction)
                await new_view.run_bot_attack(interaction=None)
            else:
                new_view = await self.replace_with_fresh_view(None)
                await new_view.run_bot_attack(interaction=None)
            return

        if respond:
            await self.replace_with_fresh_view(interaction)
        else:
            await self.replace_with_fresh_view(None)

    async def run_bot_attack(self, interaction: discord.Interaction | None):
        """
        Natalie 自動攻擊並進入玩家防守階段。

        Args:
            interaction (discord.Interaction | None): "通常為 None"
        """
        if self.finished or self.phase != "attack":
            return
        attacker = self.fighter_by_id(self.attacker_id)
        if not attacker.get("is_bot"):
            return

        # 自動發動攻擊技能
        if self.cog.skill_is_ready(attacker, "attack"):
            attacker["skill_armed"] = True
        await self.execute_attack(interaction)

    async def start_after_initiative(self, interaction: discord.Interaction | None):
        """
        先攻結束後進入第一個攻擊階段（含中毒／CD 與 bot 自動攻擊）。

        Args:
            interaction (discord.Interaction | None): "通常開戰時為 None"
        """
        if self.prepare_attack_phase():
            dead = self.fighter_by_id(self.attacker_id)
            winner = self.other_fighter(dead["user_id"])
            await self.finish_battle(winner=winner, reason="中毒致死。", interaction=interaction)
            return
        first = self.fighter_by_id(self.attacker_id)
        if first.get("is_bot"):
            await self.run_bot_attack(interaction)
            return
        if interaction is not None:
            await self.replace_with_fresh_view(interaction)
        elif self.message is not None:
            embed = self.cog.build_battle_embed(self)
            self.rebuild_buttons()
            await self.message.edit(embed=embed, view=self)

    async def on_timeout(self) -> None:
        """
        無操作逾時：當前應行動方判負。
        """
        if self.finished or self.phase == "ended":
            return
        actor_id = self.attacker_id if self.phase == "attack" else self.defender_id
        loser = self.fighter_by_id(actor_id)
        winner = self.other_fighter(actor_id)
        self.phase = "ended"
        self.finished = True
        self.result_text = f"**{loser['display_name']}** 放置過久，判負。\n**{winner['display_name']}** 獲勝！"
        embed = self.cog.build_battle_embed(self)
        if self.message is not None:
            try:
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass
        async with common.jsonio_lock:
            await self.cog.record_battle_outcome(winner, loser)
            await self.cog.clear_session(self.fighter_a["user_id"])
            if not self.fighter_b.get("is_bot"):
                await self.cog.clear_session(self.fighter_b["user_id"])


async def setup(client: commands.Bot):
    """
    載入 Juice Battle cog。

    Args:
        client (commands.Bot): "Natalie bot"
    """
    await client.add_cog(JuiceBattle(client))
