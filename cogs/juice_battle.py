import asyncio
import copy
import random

from discord import app_commands, Embed
from discord.ext import commands
from . import common
import discord


class JuiceBattle(commands.Cog):
    """Juice Battle：角色對戰、裝備背包與挑戰流程。"""

    def __init__(self, client: commands.Bot):
        self.bot = client
        self.bag_size = 99
        self.bag_page_size = 10
        self.challenge_timeout = 120.0
        self.battle_timeout = 180.0
        self.bag_view_timeout = 180.0
        self.tower_view_timeout = 300.0
        self.tower_floor_min = 1
        self.tower_lock = asyncio.Lock()
        self.tower_aborted_teams = set()
        self.default_bet = 0
        self.leaderboard_min_rounds = 1
        self.leaderboard_top_n = 3
        self.tower_leaderboard_top_n = 10
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
            "long_sword": {
                "name": "長劍",
                "hp_offset": 0,
                "atk_offset": 1,
                "def_offset": 1,
                "agi_offset": 0,
                "ability": None,
            },
            "dagger": {
                "name": "匕首",
                "hp_offset": 0,
                "atk_offset": 1,
                "def_offset": 0,
                "agi_offset": 1,
                "ability": None,
            },
            "spear": {
                "name": "長矛",
                "hp_offset": 0,
                "atk_offset": 2,
                "def_offset": 0,
                "agi_offset": 0,
                "ability": None,
            },
            "small_shield": {
                "name": "小圓盾",
                "hp_offset": 1,
                "atk_offset": 0,
                "def_offset": 1,
                "agi_offset": 0,
                "ability": {
                    "id": "shield_counter",
                    "name": "盾反",
                    "phase": "defend",
                    "cd": 1,
                    "description": "本回合防禦值與敵人攻擊值相同時，暈眩對手一回合。",
                },
            },
            "dual_blades": {
                "name": "雙刀",
                "hp_offset": 0,
                "atk_offset": 2,
                "def_offset": 0,
                "agi_offset": 1,
                "ability": None,
            },
            "blue_black_dual_blades": {
                "name": "藍黑雙刀",
                "hp_offset": 0,
                "atk_offset": 2,
                "def_offset": 0,
                "agi_offset": 2,
                "ability": {
                    "id": "starburst",
                    "name": "星爆氣流斬",
                    "phase": "attack",
                    "cd": 4,
                    "description": "可進行第二次攻擊，第二次攻擊使用閃避骰；絕地反擊時改為三次攻擊。",
                },
            },
            "intern_magic_wand": {
                "name": "實習生的魔法杖",
                "hp_offset": 1,
                "atk_offset": 1,
                "def_offset": 0,
                "agi_offset": 1,
                "ability": {
                    "id": "slime",
                    "name": "黏液",
                    "phase": "attack",
                    "cd": 2,
                    "description": "使對方這回合閃避偏移量 -1。",
                },
            },
            "holy_staff": {
                "name": "聖杖",
                "hp_offset": 3,
                "atk_offset": 0,
                "def_offset": 0,
                "agi_offset": 0,
                "ability": {
                    "id": "holy_light",
                    "name": "聖光",
                    "phase": "attack",
                    "cd": 4,
                    "description": "我方所有成員回復 3 HP。",
                },
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
            "metal_armor": {
                "name": "金屬盔甲",
                "hp_offset": 2,
                "atk_offset": 0,
                "def_offset": 1,
                "agi_offset": 0,
                "ability": None,
            },
            "thorn_armor": {
                "name": "荊棘盔甲",
                "hp_offset": 1,
                "atk_offset": 1,
                "def_offset": 0,
                "agi_offset": 0,
                "ability": {
                    "id": "thorn",
                    "name": "反傷",
                    "phase": "defend",
                    "cd": 3,
                    "description": "本回合受到傷害時，對攻擊者造成所受傷害的 50%。",
                },
            },
            "diamond_armor": {
                "name": "金剛盔甲",
                "hp_offset": 1,
                "atk_offset": 0,
                "def_offset": 3,
                "agi_offset": 0,
                "ability": None,
            },
            "cleric_robe": {
                "name": "聖職者長袍",
                "hp_offset": 4,
                "atk_offset": 0,
                "def_offset": 0,
                "agi_offset": 0,
                "ability": {
                    "id": "life_conversion",
                    "name": "生命轉換",
                    "phase": "defend",
                    "cd": 6,
                    "description": "本回合只能防禦，承受對方全部攻擊傷害後回復防禦值 HP。",
                },
            },
            "absorption_vest": {
                "name": "吸收背心",
                "hp_offset": 2,
                "atk_offset": 0,
                "def_offset": -1,
                "agi_offset": 1,
                "ability": {
                    "id": "absorption",
                    "name": "吸收",
                    "phase": "passive",
                    "cd": None,
                    "description": "受到 1 點傷害的攻擊或狀態傷害無效化。",
                },
            },
            "berserker_armor": {
                "name": "狂戰鎧甲",
                "hp_offset": -2,
                "atk_offset": 1,
                "def_offset": 0,
                "agi_offset": 1,
                "ability": {
                    "id": "berserk",
                    "name": "暴走",
                    "phase": "passive",
                    "cd": None,
                    "description": "承受 5 次傷害後，本場戰鬥攻擊偏移量 +3。",
                },
            },
            "ghost_robe": {
                "name": "幽魂長袍",
                "hp_offset": 1,
                "atk_offset": 0,
                "def_offset": 0,
                "agi_offset": 3,
                "ability": {
                    "id": "ghost",
                    "name": "幽靈化",
                    "phase": "defend",
                    "cd": 6,
                    "description": "本回合傷害無效化。",
                },
            },
            "berserker_vest": {
                "name": "狂戰背心",
                "hp_offset": -4,
                "atk_offset": 1,
                "def_offset": 0,
                "agi_offset": 3,
                "ability": {
                    "id": "desperate_counter",
                    "name": "絕地反擊",
                    "phase": "passive",
                    "cd": None,
                    "description": "生命值為 1 或 2 時，攻擊階段可進行兩次攻擊。",
                },
            },
        }
        self.tower_small_monsters = [
            {"id": "goblin", "name": "哥布林", "ability": None},
            {"id": "slime", "name": "史萊姆", "ability": None},
            {
                "id": "sticky_slime",
                "name": "黏液史萊姆",
                "ability": {
                    "id": "sticky",
                    "name": "黏呼呼",
                    "description": "攻擊造成傷害時，使對方閃避偏移量 -1，持續一回合。",
                },
            },
            {
                "id": "poison_bubble_bug",
                "name": "毒泡蟲",
                "ability": {
                    "id": "poison_immunity",
                    "name": "中毒免疫",
                    "description": "免疫中毒。",
                },
            },
            {"id": "bat", "name": "蝙蝠", "ability": None},
            {
                "id": "mushroom",
                "name": "蘑菇",
                "ability": {
                    "id": "growth",
                    "name": "增值",
                    "description": "回合開始時回復 1 HP。",
                },
            },
            {"id": "spark", "name": "火花精", "ability": None},
            {"id": "fat_rat", "name": "肥滋滋老鼠", "ability": None},
        ]
        self.tower_boss_monsters = [
            {
                "id": "hell_wraith",
                "name": "地獄厲鬼",
                "ability": {
                    "id": "hellfire",
                    "name": "地獄的業火",
                    "description": "每次攻擊後攻擊偏移量 +1；自身受到傷害時歸零。",
                },
            },
            {
                "id": "abyss_jellyfish",
                "name": "深淵水母",
                "ability": {
                    "id": "bind",
                    "name": "束縛",
                    "phase": "attack",
                    "cd": 3,
                    "description": "此次攻擊對手無法選擇閃避。",
                },
            },
            {
                "id": "lava_beetle",
                "name": "熔岩甲蟲",
                "ability": {
                    "id": "hardened_shell",
                    "name": "硬化甲殼",
                    "phase": "defend",
                    "cd": 1,
                    "description": "防禦後，若傷害為 3 以下則傷害無效化。",
                },
            },
            {
                "id": "meg",
                "name": "梅格",
                "ability": {
                    "id": "sprint",
                    "name": "大跑",
                    "phase": "defend",
                    "cd": 3,
                    "description": "本回合只能閃避，閃避偏移值變為 2 倍。",
                },
            },
            {
                "id": "old_jin",
                "name": "老金",
                "ability": {
                    "id": "referee",
                    "name": "裁判",
                    "description": "所有擲骰動作擲 2d6，取較大點數。",
                },
            },
            {
                "id": "jungle_hunter",
                "name": "叢林獵人",
                "ability": {
                    "id": "trap",
                    "name": "捕獸夾",
                    "description": "對方防禦或閃避骰點為 1 時，暈眩對方一回合並吃滿傷害。",
                },
            },
        ]

    def equipment_catalog(self) -> list[dict]:
        """
        回傳後台與掉落設定使用的非初始裝備清單。

        Returns:
            items (list[dict]): "每個項目包含 item_id、kind、name 與能力資料"
        """
        items = []
        for kind, collection in (("weapon", self.weapons), ("armor", self.armors)):
            for item_id, template in collection.items():
                if template.get("starter"):
                    continue
                ability = template.get("ability")
                items.append(
                    {
                        "item_id": item_id,
                        "kind": kind,
                        "name": template["name"],
                        "hp_offset": template["hp_offset"],
                        "atk_offset": template["atk_offset"],
                        "def_offset": template["def_offset"],
                        "agi_offset": template["agi_offset"],
                        "ability": copy.deepcopy(ability) if isinstance(ability, dict) else None,
                        "starter": bool(template.get("starter")),
                    }
                )
        return items

    def tower_monster_template(self, monster_id: str, *, boss: bool) -> dict | None:
        """
        依 ID 取得爬塔怪物定義。

        Args:
            monster_id (str): "goblin"
            boss (bool): "是否從特殊怪物池查找"

        Returns:
            monster (dict | None): "怪物名稱與技能定義"
        """
        monsters = self.tower_boss_monsters if boss else self.tower_small_monsters
        for monster in monsters:
            if monster["id"] == monster_id:
                return monster
        return None

    def build_tower_monster(self, floor: int) -> dict:
        """
        依樓層隨機建立一隻爬塔怪物。

        Args:
            floor (int): "目前樓層，例如 5"

        Returns:
            monster (dict): "包含名稱、四項數值與戰鬥狀態"
        """
        is_boss = floor % 5 == 0
        monster_pool = self.tower_boss_monsters if is_boss else self.tower_small_monsters
        template = random.choice(monster_pool)
        bonus_points = max(0, floor - 1)
        stats = [10, 0, 0, 0]
        for _ in range(bonus_points):
            stats[random.randrange(4)] += 1
        ability = copy.deepcopy(template.get("ability"))
        return {
            "id": template["id"],
            "name": template["name"],
            "floor": floor,
            "hp": stats[0],
            "max_hp": stats[0],
            "atk": stats[1],
            "defense": stats[2],
            "agi": stats[3],
            "ability": ability,
            "is_boss": is_boss,
            "attack_offset": 0,
            "skill_cd": 0,
            "skill_used_once": False,
            "stun_remaining": 0,
            "poison_remaining": 0,
            "dodge_offset": 0,
            "two_dice": template["id"] == "old_jin",
            "hardening_armed": False,
        }

    def tower_roll(self, fighter: dict, base: int, offset: int = 0, *, offset_multiplier: int = 1) -> tuple[int, int, str]:
        """
        執行爬塔用擲骰，老金會擲兩顆並取較大值。

        Args:
            fighter (dict): "玩家或怪物戰鬥狀態"
            base (int): "角色素質"
            offset (int): "裝備或技能偏移"
            offset_multiplier (int): "偏移倍率，例如梅格為 2"

        Returns:
            result (tuple[int, int, str]): "(採用骰點、總值、骰點說明)"
        """
        dice_one = random.randint(1, 6)
        if fighter.get("two_dice"):
            dice_two = random.randint(1, 6)
            dice = max(dice_one, dice_two)
            dice_text = f"2d6={dice_one}/{dice_two}→{dice}"
        else:
            dice = dice_one
            dice_text = f"1d6={dice}"
        total = dice + base + (offset * offset_multiplier)
        return dice, total, dice_text

    def tower_skill_definition(self, fighter: dict, source: str) -> dict | None:
        """
        取得爬塔角色、武器或防具技能定義。

        Args:
            fighter (dict): "玩家戰鬥狀態"
            source (str): "character、weapon 或 armor"

        Returns:
            ability (dict | None): "技能資料"
        """
        if source == "character":
            ability = self.character_ability(fighter.get("character_id"))
        else:
            ability = fighter.get(f"{source}_ability")
        return ability if isinstance(ability, dict) else None

    def tower_skill_is_ready(self, fighter: dict, source: str, phase: str) -> bool:
        """
        判斷爬塔裝備或角色技能是否可發動。

        Args:
            fighter (dict): "玩家戰鬥狀態"
            source (str): "character、weapon 或 armor"
            phase (str): "attack 或 defend"

        Returns:
            ready (bool): "技能是否可用"
        """
        ability = self.tower_skill_definition(fighter, source)
        if ability is None or ability.get("phase") != phase:
            return False
        if ability.get("cd") is None:
            return not fighter.get(f"{source}_skill_used", False)
        return int(fighter.get(f"{source}_skill_cd", 0)) <= 0

    def tower_consume_skill(self, fighter: dict, source: str) -> dict | None:
        """
        消耗一個爬塔技能並寫入 CD 或一次性使用狀態。

        Args:
            fighter (dict): "玩家戰鬥狀態"
            source (str): "character、weapon 或 armor"

        Returns:
            ability (dict | None): "消耗的技能資料"
        """
        ability = self.tower_skill_definition(fighter, source)
        if ability is None:
            return None
        if ability.get("cd") is None:
            fighter[f"{source}_skill_used"] = True
        else:
            fighter[f"{source}_skill_cd"] = int(ability["cd"])
        return ability

    def tower_prepare_skill_cooldowns(self, fighter: dict, phase: str):
        """
        在爬塔回合開始時遞減該角色指定階段的技能 CD。

        Args:
            fighter (dict): "玩家或怪物戰鬥狀態"
            phase (str): "attack 或 defend"
        """
        sources = ("character", "weapon") if phase == "attack" else ("character", "armor", "weapon")
        for source in sources:
            ability = self.tower_skill_definition(fighter, source)
            if ability and ability.get("phase") == phase:
                key = f"{source}_skill_cd"
                if int(fighter.get(key, 0)) > 0:
                    fighter[key] = int(fighter[key]) - 1

    def tower_add_hp(self, fighter: dict, amount: int):
        """
        讓爬塔戰鬥角色回復生命並限制在生命上限內。

        Args:
            fighter (dict): "玩家或怪物戰鬥狀態"
            amount (int): "回復量"
        """
        fighter["hp"] = min(fighter["max_hp"], max(0, int(fighter.get("hp", 0)) + amount))

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
            "tower_progress": None,
            "tower_records": [],
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
        if juice_battle.get("tower_progress") is not None and not isinstance(juice_battle.get("tower_progress"), dict):
            juice_battle["tower_progress"] = None
        tower_progress = juice_battle.get("tower_progress")
        if isinstance(tower_progress, dict) and "battle" not in tower_progress:
            tower_progress["battle"] = None
        if not isinstance(juice_battle.get("tower_records"), list):
            juice_battle["tower_records"] = []
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

    def equipment_stat_offsets(self, entry: dict) -> dict | None:
        """
        取得背包裝備的四項偏移；優先用實例欄位，否則用模板。

        Args:
            entry (dict): "{'item_id': 'long_sword', 'kind': 'weapon'}"

        Returns:
            offsets (dict | None): "{'hp_offset': 0, 'atk_offset': 1, 'def_offset': 1, 'agi_offset': 0}"
        """
        if not isinstance(entry, dict):
            return None
        template = self.item_template(entry.get("kind"), entry.get("item_id"))
        if template is None:
            return None
        offsets = {}
        for key in ("hp_offset", "atk_offset", "def_offset", "agi_offset"):
            if key in entry and entry[key] is not None:
                offsets[key] = int(entry[key])
            else:
                offsets[key] = int(template.get(key, 0))
        return offsets

    def serialize_equipment_instance(self, entry: dict) -> dict | None:
        """
        複製一件可交易裝備實例（含偏移快照）。

        Args:
            entry (dict): "{'item_id': 'long_sword', 'kind': 'weapon'}"

        Returns:
            instance (dict | None): "{'item_id': 'long_sword', 'hp_offset': 0}"
        """
        offsets = self.equipment_stat_offsets(entry)
        if offsets is None:
            return None
        template = self.item_template(entry.get("kind"), entry.get("item_id"))
        if template is None or template.get("starter"):
            return None
        return {
            "item_id": str(entry.get("item_id")),
            "kind": str(entry.get("kind")),
            "hp_offset": offsets["hp_offset"],
            "atk_offset": offsets["atk_offset"],
            "def_offset": offsets["def_offset"],
            "agi_offset": offsets["agi_offset"],
        }

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
            entry_offsets = self.equipment_stat_offsets(entry) if isinstance(entry, dict) else None
            if entry_offsets is None:
                continue
            offsets["hp_offset"] += entry_offsets["hp_offset"]
            offsets["atk_offset"] += entry_offsets["atk_offset"]
            offsets["def_offset"] += entry_offsets["def_offset"]
            offsets["agi_offset"] += entry_offsets["agi_offset"]
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
        weapon_id = None
        armor_id = None
        weapon_ability = None
        armor_ability = None
        if juice_battle is not None:
            bag = juice_battle.get("bag") or []
            weapon_slot = juice_battle.get("equipped_weapon_slot")
            armor_slot = juice_battle.get("equipped_armor_slot")
            for slot, kind in ((weapon_slot, "weapon"), (armor_slot, "armor")):
                if not isinstance(slot, int) or slot < 0 or slot >= len(bag):
                    continue
                entry = bag[slot]
                if not isinstance(entry, dict):
                    continue
                template = self.item_template(kind, entry.get("item_id"))
                if template is None:
                    continue
                if kind == "weapon":
                    weapon_id = entry.get("item_id")
                    weapon_ability = copy.deepcopy(template.get("ability"))
                else:
                    armor_id = entry.get("item_id")
                    armor_ability = copy.deepcopy(template.get("ability"))
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
            "weapon_id": weapon_id,
            "armor_id": armor_id,
            "weapon_ability": weapon_ability,
            "armor_ability": armor_ability,
            "character_skill_cd": 0,
            "weapon_skill_cd": 0,
            "armor_skill_cd": 0,
            "character_skill_used": False,
            "weapon_skill_used": False,
            "armor_skill_used": False,
            "tower_skill_armed": None,
            "damage_taken_count": 0,
            "berserk_triggered": False,
            "stun_remaining": 0,
            "dodge_offset": 0,
            "hellfire_offset": 0,
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

    async def notify_tower_invite_dm(self, teammate: discord.abc.User, inviter: discord.abc.User, jump_url: str):
        """
        私訊被邀請的隊友，附上爬塔邀請訊息連結。

        Args:
            teammate (discord.abc.User): "被邀請隊友"
            inviter (discord.abc.User): "發起者"
            jump_url (str): "https://discord.com/channels/..."
        """
        description = (
            f"**{inviter.display_name}** 邀請你一起挑戰 Juice Battle 爬塔！\n"
            f"請點擊下方連結回到邀請訊息，並按下「同意爬塔」。"
        )
        if jump_url:
            description += f"\n\n邀請訊息：{jump_url}"
        embed = Embed(title="Juice Battle｜爬塔邀請", description=description, color=common.bot_color)
        try:
            await teammate.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def tower_begin_session(self, interaction: discord.Interaction, progress: dict, *, edit_message: bool):
        """
        送出或更新爬塔樓層／戰鬥訊息，並標記隊伍進行中。

        Args:
            interaction (discord.Interaction): "slash 或按鈕互動"
            progress (dict): "要開始的爬塔快照"
            edit_message (bool): "True 時編輯原訊息（邀請同意後）"
        """
        view = self.tower_restore_battle(progress)
        if view is None:
            if progress.get("battle") is not None:
                progress["battle"] = None
                await self.tower_save_progress(progress)
            view = JuiceBattleTowerFloorView(cog=self, progress=progress)
            embed = self.tower_floor_embed(progress)
        else:
            embed = view.build_embed()
            embed.description = "已恢復本場戰鬥，請從目前回合繼續操作。"
        if edit_message:
            await interaction.response.edit_message(embed=embed, view=view)
            message = interaction.message
        else:
            await interaction.response.send_message(embed=embed, view=view)
            message = await interaction.original_response()
        view.message = message
        session = {
            "tower": True,
            "tower_members": [str(member_id) for member_id in progress.get("member_ids") or []],
            "guild_id": str(interaction.guild_id) if interaction.guild_id else "@me",
            "channel_id": str(message.channel.id),
            "message_id": str(message.id),
        }
        async with self.tower_lock:
            await self.tower_set_playing(
                [str(member_id) for member_id in progress.get("member_ids") or []],
                session,
            )

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
            ability = template.get("ability")
            if isinstance(ability, dict):
                value += f"\n能力：{ability.get('name', '無')}｜{ability.get('description', '')}"
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
                embed=Embed(title="Juice Battle", description="禁止自殘，要好好愛護自己哦。", color=common.bot_error_color),
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

    def tower_default_progress(self, member_ids: list[str]) -> dict:
        """
        建立一份新的爬塔進度。

        Args:
            member_ids (list[str]): "隊伍成員 ID，單人時只有一個"

        Returns:
            progress (dict): "可寫入玩家資料的爬塔快照"
        """
        floor = self.tower_floor_min
        self.tower_aborted_teams.discard(self.tower_team_key(member_ids))
        return {
            "member_ids": [str(member_id) for member_id in member_ids],
            "member_names": {},
            "floor": floor,
            "cleared_floor": 0,
            "pending_cake": 0,
            "pending_equipment": [],
            "member_hp": {},
            "dead_ids": [],
            "monster": self.build_tower_monster(floor),
            "battle": None,
        }

    async def tower_load_shared_progress(self, member_ids: list[str]) -> dict | None:
        """
        從任一隊員資料載入同一組隊伍的爬塔進度。

        Args:
            member_ids (list[str]): "預期的隊伍成員 ID"

        Returns:
            progress (dict | None): "找到且成員相同的爬塔進度"
        """
        expected_ids = {str(member_id) for member_id in member_ids}
        for member_id in member_ids:
            user_data = await self.load_user(str(member_id))
            progress = user_data["juice_battle"].get("tower_progress")
            if not isinstance(progress, dict):
                continue
            stored_ids = {str(value) for value in progress.get("member_ids") or []}
            if stored_ids == expected_ids:
                return copy.deepcopy(progress)
        return None

    async def tower_find_progress_for_user(self, userid: str) -> dict | None:
        """
        讀取玩家目前的未完成爬塔進度。

        Args:
            userid (str): "410847926236086272"

        Returns:
            progress (dict | None): "玩家保存的爬塔進度"
        """
        user_data = await self.load_user(userid)
        progress = user_data["juice_battle"].get("tower_progress")
        return copy.deepcopy(progress) if isinstance(progress, dict) else None

    async def tower_save_progress(self, progress: dict):
        """
        將同一份爬塔進度同步寫入所有隊員。

        Args:
            progress (dict): "要保存的爬塔快照"
        """
        member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
        if self.tower_is_aborted(member_ids):
            return
        for member_id in member_ids:
            user_data = await self.load_user(member_id)
            user_data["juice_battle"]["tower_progress"] = copy.deepcopy(progress)
            await common.mongo_storage.replace_user(member_id, user_data)

    async def tower_save_battle(self, view: "JuiceBattleTowerView"):
        """
        將目前爬塔戰鬥 View 的完整狀態同步保存給所有隊員。

        Args:
            view (JuiceBattleTowerView): "進行中的爬塔戰鬥 View"
        """
        progress = copy.deepcopy(view.progress)
        progress["battle"] = view.battle_snapshot()
        await self.tower_save_progress(progress)

    def tower_restore_battle(self, progress: dict) -> "JuiceBattleTowerView | None":
        """
        依已保存的戰鬥快照還原爬塔戰鬥 View。

        Args:
            progress (dict): "包含 battle 快照的爬塔進度"

        Returns:
            view (JuiceBattleTowerView | None): "還原成功的 View"
        """
        battle = progress.get("battle")
        if not isinstance(battle, dict):
            return None
        fighters = battle.get("fighters")
        monster = battle.get("monster")
        if not isinstance(fighters, list) or not isinstance(monster, dict):
            return None
        view = JuiceBattleTowerView(
            cog=self,
            progress=progress,
            fighters=copy.deepcopy(fighters),
            monster=copy.deepcopy(monster),
        )
        view.turn_order = [str(user_id) for user_id in battle.get("turn_order") or []]
        view.current_index = int(battle.get("current_index", 0))
        view.round_number = int(battle.get("round_number", 1))
        view.phase = str(battle.get("phase") or "player_attack")
        view.current_actor_id = (
            str(battle["current_actor_id"])
            if battle.get("current_actor_id") is not None
            else None
        )
        view.pending_target_id = (
            str(battle["pending_target_id"])
            if battle.get("pending_target_id") is not None
            else None
        )
        view.pending_attack_total = (
            int(battle["pending_attack_total"])
            if battle.get("pending_attack_total") is not None
            else None
        )
        view.pending_attack_dice = str(battle.get("pending_attack_dice") or "")
        view.pending_bind = bool(battle.get("pending_bind", False))
        view.last_attack_damage = int(battle.get("last_attack_damage", 0))
        view.log_text = str(battle.get("log_text") or "")
        if view.monster_turn_id not in view.turn_order:
            view.turn_order.append(view.monster_turn_id)
            if view.phase == "player_defend":
                view.current_index = len(view.turn_order)
        view.finished = False
        view.rebuild_buttons()
        return view

    async def tower_set_playing(self, member_ids: list[str], session: dict):
        """
        標記爬塔隊伍正在進行中。

        Args:
            member_ids (list[str]): "隊伍成員 ID"
            session (dict): "爬塔訊息 session"
        """
        for member_id in member_ids:
            await self.set_playing_session(str(member_id), copy.deepcopy(session))

    async def tower_clear_progress(self, member_ids: list[str]):
        """
        清除隊伍爬塔進度、暫存獎勵與進行中鎖定。

        Args:
            member_ids (list[str]): "隊伍成員 ID"
        """
        for member_id in member_ids:
            user_data = await self.load_user(str(member_id))
            juice_battle = user_data["juice_battle"]
            juice_battle["playing"] = False
            juice_battle.pop("session", None)
            juice_battle["tower_progress"] = None
            await common.mongo_storage.replace_user(str(member_id), user_data)

    def tower_team_key(self, member_ids) -> frozenset:
        """
        將隊員 ID 轉成可用來比對隊伍的 key。

        Args:
            member_ids: "['4108', '4109']"

        Returns:
            key (frozenset): "frozenset({'4108', '4109'})"
        """
        return frozenset(str(member_id) for member_id in (member_ids or []) if str(member_id))

    def tower_is_aborted(self, member_ids) -> bool:
        """
        判斷隊伍是否已被後台強制結束。

        Args:
            member_ids: "['4108']"

        Returns:
            aborted (bool): "True"
        """
        key = self.tower_team_key(member_ids)
        return bool(key) and key in self.tower_aborted_teams

    async def tower_reject_if_aborted(self, interaction: discord.Interaction, member_ids) -> bool:
        """
        若隊伍已被強制結束，回覆提示並拒絕操作。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            member_ids: "['4108']"

        Returns:
            rejected (bool): "已被拒絕時為 True"
        """
        if not self.tower_is_aborted(member_ids):
            return False
        embed = Embed(
            title="Juice Battle｜爬塔",
            description="這次爬塔已被管理員強制結束。",
            color=common.bot_error_color,
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return True

    async def tower_list_active_runs(self) -> list[dict]:
        """
        掃描資料庫，列出目前尚未清空的爬塔隊伍。

        Returns:
            runs (list[dict]): "[{'member_ids': [...], 'floor': 3, ...}]"
        """
        collection = common.mongo_storage.get_collection("userdata")
        if collection is None:
            return []
        runs_by_key = {}
        cursor = collection.find(
            {"juice_battle.tower_progress": {"$type": "object"}},
            {
                "_id": 1,
                "juice_battle.tower_progress": 1,
                "juice_battle.session": 1,
                "juice_battle.playing": 1,
            },
        )
        async for document in cursor:
            juice_battle = document.get("juice_battle") or {}
            progress = juice_battle.get("tower_progress")
            if not isinstance(progress, dict):
                continue
            member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
            if not member_ids:
                continue
            key = self.tower_team_key(member_ids)
            if key in runs_by_key:
                continue
            member_names = progress.get("member_names") if isinstance(progress.get("member_names"), dict) else {}
            members = []
            for member_id in member_ids:
                members.append({
                    "user_id": member_id,
                    "name": str(member_names.get(member_id) or member_id),
                })
            monster = progress.get("monster") if isinstance(progress.get("monster"), dict) else {}
            session = juice_battle.get("session") if isinstance(juice_battle.get("session"), dict) else {}
            runs_by_key[key] = {
                "team_key": ",".join(sorted(key)),
                "member_ids": member_ids,
                "members": members,
                "floor": int(progress.get("floor", self.tower_floor_min)),
                "cleared_floor": int(progress.get("cleared_floor", 0)),
                "monster_name": str(monster.get("name") or "未知怪物"),
                "playing": bool(juice_battle.get("playing")),
                "session_url": self.session_jump_url(session) if session.get("tower") else None,
            }
        runs = list(runs_by_key.values())
        runs.sort(key=lambda entry: (-int(entry["floor"]), entry["team_key"]))
        return runs

    async def tower_force_end_run(self, member_ids: list[str]) -> dict:
        """
        後台強制結束指定隊伍的爬塔，並清空進度。

        Args:
            member_ids (list[str]): "['4108', '4109']"

        Returns:
            payload (dict): "{'ok': True, 'message': '...'}"
        """
        normalized_ids = [str(member_id) for member_id in member_ids if str(member_id)]
        key = self.tower_team_key(normalized_ids)
        if not key:
            return {"ok": False, "error": "缺少隊伍成員"}

        # 先標記中止，避免舊 View 再把進度寫回
        self.tower_aborted_teams.add(key)
        session = None
        found = False
        async with self.tower_lock:
            for member_id in sorted(key):
                user_data = await self.load_user(member_id)
                progress = user_data["juice_battle"].get("tower_progress")
                if not isinstance(progress, dict):
                    continue
                progress_key = self.tower_team_key(progress.get("member_ids") or [])
                if progress_key != key:
                    continue
                found = True
                current_session = user_data["juice_battle"].get("session")
                if isinstance(current_session, dict) and current_session.get("tower"):
                    session = current_session
            if not found:
                self.tower_aborted_teams.discard(key)
                return {"ok": False, "error": "找不到這支隊伍的爬塔進度"}
            await self.tower_clear_progress(list(key))

        # 盡力把 Discord 訊息標成已強制結束
        if isinstance(session, dict):
            channel_id = session.get("channel_id")
            message_id = session.get("message_id")
            if channel_id is not None and message_id is not None:
                channel = self.bot.get_channel(int(channel_id))
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(int(channel_id))
                    except Exception:
                        channel = None
                if channel is not None:
                    try:
                        message = await channel.fetch_message(int(message_id))
                        await message.edit(
                            embed=Embed(
                                title="Juice Battle｜爬塔",
                                description="這次爬塔已被管理員強制結束，進度已清空。",
                                color=common.bot_error_color,
                            ),
                            view=None,
                        )
                    except Exception:
                        pass

        payload = await self.tower_admin_payload()
        payload["message"] = "已強制結束這次爬塔。"
        return payload

    async def tower_pick_equipment(self, floor: int) -> str | None:
        """
        依後台設定抽取指定樓層的裝備。

        Args:
            floor (int): "剛通關的樓層"

        Returns:
            item_id (str | None): "抽到的裝備 ID，沒有設定時為 None"
        """
        collection = common.mongo_storage.get_collection("juice_battle_tower")
        document = await collection.find_one({"_id": "settings"})
        pools = document.get("drop_pools") if isinstance(document, dict) else {}
        if not isinstance(pools, dict):
            return None
        floor_key = str(floor)
        selected = pools.get(floor_key) if floor_key in pools else pools.get("default")
        if not isinstance(selected, list):
            return None
        valid_ids = {
            item["item_id"]
            for item in self.equipment_catalog()
            if item["item_id"] in selected
        }
        choices = [item_id for item_id in selected if item_id in valid_ids]
        return random.choice(choices) if choices else None

    def normalize_tower_drop_pools(self, raw) -> dict:
        """
        正規化爬塔通用與指定樓層掉落池。

        Args:
            raw: "後台送出的 {'default': [...], '5': [...]}"

        Returns:
            pools (dict): "只包含合法裝備 ID 與正的 5 倍數樓層"
        """
        source = raw if isinstance(raw, dict) else {}
        valid_ids = {item["item_id"] for item in self.equipment_catalog()}
        pools = {}
        for key, values in source.items():
            key_text = str(key)
            if key_text != "default":
                try:
                    floor = int(key_text)
                except (TypeError, ValueError):
                    continue
                if floor < 5 or floor % 5 != 0:
                    continue
                key_text = str(floor)
            if not isinstance(values, list):
                continue
            pools[key_text] = list(dict.fromkeys(str(item_id) for item_id in values if str(item_id) in valid_ids))
        pools.setdefault("default", [])
        return pools

    async def tower_admin_payload(self) -> dict:
        """
        建立爬塔後台頁面資料。

        Returns:
            payload (dict): "裝備清單、掉落池與進行中爬塔"
        """
        collection = common.mongo_storage.get_collection("juice_battle_tower")
        document = await collection.find_one({"_id": "settings"})
        raw_pools = document.get("drop_pools") if isinstance(document, dict) else {}
        return {
            "ok": True,
            "equipment": self.equipment_catalog(),
            "drop_pools": self.normalize_tower_drop_pools(raw_pools),
            "active_runs": await self.tower_list_active_runs(),
        }

    async def save_tower_settings(self, raw_pools) -> dict:
        """
        驗證並保存爬塔裝備掉落設定。

        Args:
            raw_pools: "後台送出的掉落池字典"

        Returns:
            payload (dict): "保存後的設定與裝備清單"
        """
        pools = self.normalize_tower_drop_pools(raw_pools)
        collection = common.mongo_storage.get_collection("juice_battle_tower")
        await collection.replace_one({"_id": "settings"}, {"_id": "settings", "drop_pools": pools}, upsert=True)
        payload = await self.tower_admin_payload()
        payload["message"] = "已儲存爬塔裝備掉落設定。"
        return payload

    def tower_build_party(self, progress: dict, user_data_map: dict[str, dict]) -> list[dict]:
        """
        依爬塔進度建立本層玩家戰鬥狀態。

        Args:
            progress (dict): "目前爬塔快照"
            user_data_map (dict[str, dict]): "隊員 ID 對應使用者資料"

        Returns:
            fighters (list[dict]): "玩家戰鬥角色清單"
        """
        fighters = []
        member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
        saved_hp = progress.get("member_hp") if isinstance(progress.get("member_hp"), dict) else {}
        dead_ids = {str(member_id) for member_id in progress.get("dead_ids") or []}
        member_names = progress.setdefault("member_names", {})
        for member_id in member_ids:
            user_data = user_data_map[member_id]
            juice_battle = user_data["juice_battle"]
            display_name = str(member_names.get(member_id) or member_id)
            fighter = self.build_fighter(
                user_id=member_id,
                display_name=display_name,
                character_id=juice_battle["character_id"],
                juice_battle=juice_battle,
                is_bot=False,
            )
            if member_id in saved_hp:
                fighter["hp"] = min(fighter["max_hp"], max(0, int(saved_hp[member_id])))
            if member_id in dead_ids:
                fighter["hp"] = min(fighter["max_hp"], 3)
            fighters.append(fighter)
        return fighters

    def tower_floor_embed(self, progress: dict, *, log_text: str = "") -> Embed:
        """
        建立爬塔樓層入口或通關後的資訊 embed。

        Args:
            progress (dict): "目前爬塔快照"
            log_text (str): "可選的上一場結果說明"

        Returns:
            embed (Embed): "樓層資訊"
        """
        monster = progress.get("monster") or {}
        floor = int(progress.get("floor", self.tower_floor_min))
        ability = monster.get("ability") if isinstance(monster.get("ability"), dict) else None
        description = f"目前第 **{floor} 層**，遇到 **{monster.get('name', '未知怪物')}**。"
        if floor == self.tower_floor_min:
            description += "\n這是第一層，不能逃跑。"
        else:
            description += "\n可以挑戰怪物，或帶著目前累積的戰利品逃跑。"
        if log_text:
            description += f"\n\n{log_text}"
        embed = Embed(title="Juice Battle｜爬塔", description=description, color=common.bot_color)
        embed.add_field(
            name="怪物資訊",
            value=(
                f"生命 **{monster.get('hp', 0)}/{monster.get('max_hp', 0)}**\n"
                f"攻擊 {monster.get('atk', 0)}｜防禦 {monster.get('defense', 0)}｜敏捷 {monster.get('agi', 0)}"
            ),
            inline=False,
        )
        if ability:
            embed.add_field(
                name=f"技能：{ability.get('name', '被動')}",
                value=str(ability.get("description") or "—"),
                inline=False,
            )
        pending_equipment = progress.get("pending_equipment") or []
        pending_names = []
        for item_id in pending_equipment:
            template = self.item_template("weapon", item_id) or self.item_template("armor", item_id)
            pending_names.append(template["name"] if template else str(item_id))
        pending_text = "、".join(pending_names)
        embed.add_field(
            name="本次暫存戰利品",
            value=f"蛋糕：**{int(progress.get('pending_cake', 0))}** {common.cake_emoji}\n裝備：{pending_text or '無'}",
            inline=False,
        )
        return embed

    def tower_party_names(self, progress: dict) -> list[str]:
        """
        取得排行榜與獎勵訊息使用的隊伍名稱。

        Args:
            progress (dict): "爬塔快照"

        Returns:
            names (list[str]): "隊員顯示名稱"
        """
        member_names = progress.get("member_names") if isinstance(progress.get("member_names"), dict) else {}
        return [
            str(member_names.get(str(member_id)) or member_id)
            for member_id in progress.get("member_ids") or []
        ]

    async def tower_record_success(self, progress: dict):
        """
        為成功逃跑的單人或雙人爬塔寫入最高紀錄。

        Args:
            progress (dict): "已成功結算的爬塔快照"
        """
        member_ids = sorted(str(member_id) for member_id in progress.get("member_ids") or [])
        record = {
            "mode": "solo" if len(member_ids) == 1 else "party",
            "member_ids": member_ids,
            "floor": int(progress.get("cleared_floor", 0)),
        }
        for member_id in member_ids:
            user_data = await self.load_user(member_id)
            records = user_data["juice_battle"].get("tower_records")
            if not isinstance(records, list):
                records = []
            replaced = False
            for old_record in records:
                old_ids = sorted(str(value) for value in old_record.get("member_ids") or []) if isinstance(old_record, dict) else []
                if old_ids != member_ids:
                    continue
                old_record["floor"] = max(int(old_record.get("floor", 0)), record["floor"])
                replaced = True
                break
            if not replaced:
                records.append(copy.deepcopy(record))
            user_data["juice_battle"]["tower_records"] = records
            await common.mongo_storage.replace_user(member_id, user_data)

    async def tower_grant_rewards(self, progress: dict, recipient_ids: list[str]):
        """
        將爬塔暫存獎勵發給隊員並寫入成功紀錄。

        Args:
            progress (dict): "成功逃跑的爬塔快照"
            recipient_ids (list[str]): "每件裝備的指定領取者 ID"
        """
        member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
        user_data_map = {}
        for member_id in member_ids:
            user_data_map[member_id] = await self.load_user(member_id)
            user_data_map[member_id]["cake"] = int(user_data_map[member_id].get("cake", 0)) + int(progress.get("pending_cake", 0))
        pending_equipment = [str(item_id) for item_id in progress.get("pending_equipment") or []]
        for item_id, recipient_id in zip(pending_equipment, recipient_ids):
            target_id = str(recipient_id)
            if target_id not in user_data_map:
                target_id = member_ids[0]
            target_order = [target_id] + [member_id for member_id in member_ids if member_id != target_id]
            selected_target = None
            selected_slot = None
            for candidate_id in target_order:
                candidate_bag = user_data_map[candidate_id]["juice_battle"]["bag"]
                candidate_slot = next((index for index, entry in enumerate(candidate_bag) if entry is None), None)
                if candidate_slot is not None:
                    selected_target = candidate_id
                    selected_slot = candidate_slot
                    break
            if selected_target is None:
                continue
            bag = user_data_map[selected_target]["juice_battle"]["bag"]
            if selected_slot is not None:
                kind = "weapon" if item_id in self.weapons else "armor"
                bag[selected_slot] = {"item_id": item_id, "kind": kind}
        for member_id, user_data in user_data_map.items():
            juice_battle = user_data["juice_battle"]
            juice_battle["playing"] = False
            juice_battle.pop("session", None)
            juice_battle["tower_progress"] = None
            await common.mongo_storage.replace_user(member_id, user_data)
        await self.tower_record_success(progress)

    async def tower_finish_defeat(self, view: "JuiceBattleTowerView", reason: str):
        """
        清除全員死亡的爬塔進度。

        Args:
            view (JuiceBattleTowerView): "結束中的爬塔戰鬥 View"
            reason (str): "顯示給玩家的失敗原因"
        """
        if view.finished:
            return
        view.finished = True
        view.rebuild_buttons()
        if view.message is not None:
            await view.message.edit(
                embed=Embed(
                    title="Juice Battle｜爬塔失敗",
                    description=f"{reason}\n本次爬塔的蛋糕、裝備與進度全部消失。",
                    color=common.bot_error_color,
                ),
                view=None,
            )
        await self.tower_clear_progress(view.member_ids)
        view.stop()

    async def tower_finish_floor(self, view: "JuiceBattleTowerView", log_text: str):
        """
        結算一層爬塔戰鬥並顯示下一層入口。

        Args:
            view (JuiceBattleTowerView): "已擊敗怪物的爬塔戰鬥 View"
            log_text (str): "本層戰鬥紀錄"
        """
        if view.finished:
            return
        view.finished = True
        progress = copy.deepcopy(view.progress)
        progress.pop("battle", None)
        floor = int(progress.get("floor", self.tower_floor_min))
        progress["cleared_floor"] = floor
        cake_reward = int(round(800 * floor * random.uniform(0.9, 1.1)))
        progress["pending_cake"] = int(progress.get("pending_cake", 0)) + cake_reward
        equipment_reward = None
        if floor % 5 == 0:
            item_id = await self.tower_pick_equipment(floor)
            if item_id:
                progress.setdefault("pending_equipment", []).append(item_id)
                equipment_reward = item_id
        progress["member_hp"] = {fighter["user_id"]: max(0, int(fighter["hp"])) for fighter in view.fighters}
        progress["dead_ids"] = [fighter["user_id"] for fighter in view.fighters if fighter["hp"] <= 0]
        progress["floor"] = floor + 1
        progress["monster"] = self.build_tower_monster(floor + 1)
        await self.tower_save_progress(progress)
        view.stop()
        view.rebuild_buttons()
        result_embed = view.build_embed()
        result_embed.title = f"Juice Battle｜爬塔第 {floor} 層通關"
        result_embed.description = "怪物已死亡，本層挑戰成功！"
        equipment_name = "無"
        if equipment_reward:
            equipment_template = (
                self.item_template("weapon", equipment_reward)
                or self.item_template("armor", equipment_reward)
            )
            equipment_name = equipment_template["name"] if equipment_template else str(equipment_reward)
        result_embed.add_field(
            name="戰利品",
            value=(
                f"蛋糕：+{cake_reward} {common.cake_emoji}"
                f"（目前累積 {int(progress.get('pending_cake', 0))}）\n"
                f"裝備：{equipment_name}"
                f"（目前累積 {len(progress.get('pending_equipment') or [])} 件）"
            ),
            inline=False,
        )
        next_view = JuiceBattleTowerNextFloorView(cog=self, progress=progress)
        next_view.message = view.message
        await view.message.edit(embed=result_embed, view=next_view)

    async def tower_start_battle(self, interaction: discord.Interaction, progress: dict):
        """
        從樓層入口建立爬塔戰鬥 View。

        Args:
            interaction (discord.Interaction): "樓層按鈕互動"
            progress (dict): "目前爬塔快照"
        """
        user_data_map = {}
        for member_id in progress.get("member_ids") or []:
            user_data_map[str(member_id)] = await self.load_user(str(member_id))
        fighters = self.tower_build_party(progress, user_data_map)
        monster = copy.deepcopy(progress.get("monster") or self.build_tower_monster(int(progress["floor"])))
        view = JuiceBattleTowerView(
            cog=self,
            progress=progress,
            fighters=fighters,
            monster=monster,
        )
        view.message = interaction.message
        await interaction.response.edit_message(embed=view.build_embed(), view=view)
        await view.begin()

    async def tower_escape(self, interaction: discord.Interaction, progress: dict):
        """
        處理玩家在樓層入口按下逃跑。

        Args:
            interaction (discord.Interaction): "逃跑按鈕互動"
            progress (dict): "目前爬塔快照"
        """
        pending_equipment = [str(item_id) for item_id in progress.get("pending_equipment") or []]
        member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
        if len(member_ids) == 1 or not pending_equipment:
            recipients = [member_ids[0]] * len(pending_equipment) if member_ids else []
            await self.tower_grant_rewards(progress, recipients)
            await interaction.response.edit_message(
                embed=Embed(
                    title="Juice Battle｜爬塔結算",
                    description=(
                        f"已逃跑並取得 **{int(progress.get('pending_cake', 0))}** {common.cake_emoji}。\n"
                        f"最高通關：第 **{int(progress.get('cleared_floor', 0))}** 層。"
                    ),
                    color=common.bot_color,
                ),
                view=None,
            )
            return
        view = JuiceBattleTowerRewardView(cog=self, progress=progress, pending_index=0, recipients=[])
        view.message = interaction.message
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @app_commands.command(name="juice_battle_tower", description="挑戰 Juice Battle 爬塔")
    @app_commands.describe(teammate="可選隊友，不能是機器人")
    @app_commands.rename(teammate="隊友")
    async def juice_battle_tower(self, interaction: discord.Interaction, teammate: discord.Member | None = None):
        """
        開始或繼續單人／雙人 Juice Battle 爬塔；雙人需隊友同意。

        Args:
            interaction (discord.Interaction): "slash 互動"
            teammate (discord.Member | None): "可選的隊友"
        """
        userid = str(interaction.user.id)
        if teammate is not None and (teammate.bot or str(teammate.id) == userid):
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle｜爬塔", description="隊友不能是自己或機器人。", color=common.bot_error_color),
                ephemeral=True,
            )
            return

        async with self.tower_lock:
            own_data = await self.load_user(userid)
            own_juice = own_data["juice_battle"]
            own_progress = own_juice.get("tower_progress")
            if own_juice.get("playing"):
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle｜爬塔",
                        description=self.playing_block_description(own_juice),
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
                return

            # 決定隊伍成員與進度
            if isinstance(own_progress, dict):
                stored_ids = [str(member_id) for member_id in own_progress.get("member_ids") or []]
                if teammate is None:
                    if len(stored_ids) > 1 and userid in stored_ids:
                        other_id = next(member_id for member_id in stored_ids if member_id != userid)
                        if interaction.guild is not None:
                            teammate = interaction.guild.get_member(int(other_id))
                        if teammate is None:
                            try:
                                teammate = await interaction.client.fetch_user(int(other_id))
                            except Exception:
                                await interaction.response.send_message(
                                    embed=Embed(
                                        title="Juice Battle｜爬塔",
                                        description="找不到你的爬塔隊友，請稍後再試。",
                                        color=common.bot_error_color,
                                    ),
                                    ephemeral=True,
                                )
                                return
                    member_ids = stored_ids
                else:
                    member_ids = [userid, str(teammate.id)]
                    if set(member_ids) != set(stored_ids):
                        await interaction.response.send_message(
                            embed=Embed(
                                title="Juice Battle｜爬塔",
                                description="你目前的進度屬於另一組隊伍。",
                                color=common.bot_error_color,
                            ),
                            ephemeral=True,
                        )
                        return
                progress = copy.deepcopy(own_progress)
            else:
                member_ids = [userid] if teammate is None else [userid, str(teammate.id)]
                requested_ids = {str(member_id) for member_id in member_ids}
                for member_id in member_ids:
                    member_data = await self.load_user(str(member_id))
                    existing_progress = member_data["juice_battle"].get("tower_progress")
                    if not isinstance(existing_progress, dict):
                        continue
                    existing_ids = {str(value) for value in existing_progress.get("member_ids") or []}
                    if existing_ids != requested_ids:
                        await interaction.response.send_message(
                            embed=Embed(
                                title="Juice Battle｜爬塔",
                                description=f"<@{member_id}> 目前已有其他隊伍的未完成爬塔進度。",
                                color=common.bot_error_color,
                            ),
                            ephemeral=True,
                        )
                        return
                progress = await self.tower_load_shared_progress(member_ids)

            # 雙人：送出邀請，等隊友同意後再開始
            if len(member_ids) > 1:
                if teammate is None:
                    await interaction.response.send_message(
                        embed=Embed(
                            title="Juice Battle｜爬塔",
                            description="雙人爬塔需要指定隊友。",
                            color=common.bot_error_color,
                        ),
                        ephemeral=True,
                    )
                    return
                for member_id in member_ids:
                    member_data = await self.load_user(str(member_id))
                    if member_data["juice_battle"].get("playing"):
                        await interaction.response.send_message(
                            embed=Embed(
                                title="Juice Battle｜爬塔",
                                description=f"<@{member_id}> 目前正在其他 Juice Battle 中。",
                                color=common.bot_error_color,
                            ),
                            ephemeral=True,
                        )
                        return
                embed = Embed(
                    title="Juice Battle｜爬塔邀請",
                    description=(
                        f"{interaction.user.mention} 邀請 {teammate.mention} 一起爬塔！\n"
                        f"請 {teammate.mention} 按下「同意爬塔」開始。"
                    ),
                    color=common.bot_color,
                )
                view = JuiceBattleTowerInviteView(
                    cog=self,
                    inviter_id=userid,
                    teammate_id=str(teammate.id),
                    inviter_name=interaction.user.display_name,
                    teammate_name=teammate.display_name,
                    existing_progress=copy.deepcopy(progress) if isinstance(progress, dict) else None,
                )
                await interaction.response.send_message(embed=embed, view=view)
                message = await interaction.original_response()
                view.message = message
                await self.notify_tower_invite_dm(teammate, interaction.user, message.jump_url)
                return

            # 單人：直接開始或繼續
            if progress is None:
                progress = self.tower_default_progress(member_ids)
            progress.setdefault("member_names", {})[userid] = interaction.user.display_name
            await self.tower_save_progress(progress)

        await self.tower_begin_session(interaction, progress, edit_message=False)

    @app_commands.command(name="juice_battle_leaderboard", description="Juice Battle 勝率與爬塔排行榜")
    async def juice_battle_leaderboard(self, interaction: discord.Interaction):
        """
        顯示每個角色勝率前三名、自己的角色戰績與爬塔最高通關紀錄。

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

            # 收集並去重成功逃跑的爬塔最高紀錄
            tower_records = {}
            if collection is not None:
                async for document in collection.find(
                    {"juice_battle.tower_records": {"$exists": True}},
                    {"_id": 1, "juice_battle.tower_records": 1},
                ):
                    records = (document.get("juice_battle") or {}).get("tower_records") or []
                    if not isinstance(records, list):
                        continue
                    for record in records:
                        if not isinstance(record, dict):
                            continue
                        member_ids = sorted(str(member_id) for member_id in record.get("member_ids") or [])
                        if not member_ids or any(not member_id.isdigit() for member_id in member_ids):
                            continue
                        key = "|".join(member_ids)
                        floor = int(record.get("floor", 0))
                        old_record = tower_records.get(key)
                        if old_record is None or floor > int(old_record.get("floor", 0)):
                            tower_records[key] = {
                                "member_ids": member_ids,
                                "floor": floor,
                                "mode": "solo" if len(member_ids) == 1 else "party",
                            }

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

        # 爬塔最高通關紀錄
        tower_lines = []
        sorted_tower_records = sorted(
            tower_records.values(),
            key=lambda record: (int(record["floor"]), record["member_ids"]),
            reverse=True,
        )
        for index, record in enumerate(sorted_tower_records[: self.tower_leaderboard_top_n]):
            names = []
            for member_id in record["member_ids"]:
                member = interaction.guild.get_member(int(member_id)) if interaction.guild else None
                user_object = member or self.bot.get_user(int(member_id))
                names.append(user_object.display_name if user_object else member_id)
            label = names[0] if len(names) == 1 else f"{names[0]} 的隊伍：{'、'.join(names)}"
            tower_lines.append(f"{index + 1}. {label}｜最高第 **{record['floor']} 層**")
        embed.add_field(
            name="爬塔最高通關紀錄",
            value="\n".join(tower_lines) if tower_lines else "尚無成功逃跑紀錄",
            inline=False,
        )

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


class JuiceBattleTowerInviteView(discord.ui.View):
    """雙人爬塔邀請，需隊友同意後才開始。"""

    def __init__(
        self,
        *,
        cog: JuiceBattle,
        inviter_id: str,
        teammate_id: str,
        inviter_name: str,
        teammate_name: str,
        existing_progress: dict | None,
    ):
        """
        建立爬塔邀請 View。

        Args:
            cog (JuiceBattle): "Juice Battle cog"
            inviter_id (str): "發起者 ID"
            teammate_id (str): "被邀請隊友 ID"
            inviter_name (str): "發起者顯示名稱"
            teammate_name (str): "隊友顯示名稱"
            existing_progress (dict | None): "續爬進度；新開局為 None"
        """
        super().__init__(timeout=cog.challenge_timeout)
        self.cog = cog
        self.inviter_id = inviter_id
        self.teammate_id = teammate_id
        self.inviter_name = inviter_name
        self.teammate_name = teammate_name
        self.existing_progress = copy.deepcopy(existing_progress) if isinstance(existing_progress, dict) else None
        self.message: discord.Message | None = None
        self.accepted = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        僅被邀請的隊友可按同意。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "是否允許操作"
        """
        if str(interaction.user.id) == self.teammate_id:
            return True
        await interaction.response.send_message(
            embed=Embed(title="Juice Battle｜爬塔", description="只有被邀請的隊友可以同意。", color=common.bot_error_color),
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="同意爬塔", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        隊友同意後建立或恢復爬塔進度並開始。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            button (discord.ui.Button): "同意爬塔"
        """
        if self.accepted:
            return
        member_ids = [self.inviter_id, self.teammate_id]
        async with self.cog.tower_lock:
            for member_id in member_ids:
                member_data = await self.cog.load_user(member_id)
                if member_data["juice_battle"].get("playing"):
                    await interaction.response.send_message(
                        embed=Embed(
                            title="Juice Battle｜爬塔",
                            description=f"<@{member_id}> 目前正在其他 Juice Battle 中。",
                            color=common.bot_error_color,
                        ),
                        ephemeral=True,
                    )
                    return
                existing_progress = member_data["juice_battle"].get("tower_progress")
                if not isinstance(existing_progress, dict):
                    continue
                existing_ids = {str(value) for value in existing_progress.get("member_ids") or []}
                if existing_ids != set(member_ids):
                    await interaction.response.send_message(
                        embed=Embed(
                            title="Juice Battle｜爬塔",
                            description=f"<@{member_id}> 目前已有其他隊伍的未完成爬塔進度。",
                            color=common.bot_error_color,
                        ),
                        ephemeral=True,
                    )
                    return

            if self.existing_progress is not None:
                progress = await self.cog.tower_load_shared_progress(member_ids)
                if progress is None:
                    await interaction.response.send_message(
                        embed=Embed(
                            title="Juice Battle｜爬塔",
                            description="這組隊伍的爬塔進度已不存在，請重新發起邀請。",
                            color=common.bot_error_color,
                        ),
                        ephemeral=True,
                    )
                    return
            else:
                progress = await self.cog.tower_load_shared_progress(member_ids)
                if progress is None:
                    progress = self.cog.tower_default_progress(member_ids)

            progress.setdefault("member_names", {})
            progress["member_names"][self.inviter_id] = self.inviter_name
            progress["member_names"][self.teammate_id] = interaction.user.display_name
            await self.cog.tower_save_progress(progress)
            self.accepted = True
            button.disabled = True

        await self.cog.tower_begin_session(interaction, progress, edit_message=True)
        self.stop()

    async def on_timeout(self) -> None:
        """
        邀請逾時後取消按鈕。
        """
        if self.accepted:
            return
        for child in self.children:
            child.disabled = True
        if self.message is None:
            return
        embed = Embed(
            title="Juice Battle｜爬塔邀請",
            description=f"{self.inviter_name} 對 {self.teammate_name} 的爬塔邀請已逾時取消。",
            color=common.bot_error_color,
        )
        try:
            await self.message.edit(embed=embed, view=self)
        except Exception:
            pass


class JuiceBattleTowerChallengeButton(discord.ui.Button):
    """爬塔樓層挑戰按鈕。"""

    def __init__(self):
        """建立挑戰按鈕。"""
        super().__init__(label="挑戰", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        """
        開始挑戰目前樓層怪物。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerFloorView = self.view  # type: ignore[assignment]
        await view.on_challenge(interaction)


class JuiceBattleTowerEscapeButton(discord.ui.Button):
    """爬塔樓層逃跑按鈕。"""

    def __init__(self):
        """建立逃跑按鈕。"""
        super().__init__(label="逃跑", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        """
        帶著暫存戰利品離開爬塔。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerFloorView = self.view  # type: ignore[assignment]
        await view.on_escape(interaction)


class JuiceBattleTowerFloorView(discord.ui.View):
    """爬塔樓層入口的挑戰／逃跑介面。"""

    def __init__(self, *, cog: JuiceBattle, progress: dict):
        """
        建立樓層入口 View。

        Args:
            cog (JuiceBattle): "Juice Battle cog"
            progress (dict): "目前爬塔快照"
        """
        super().__init__(timeout=cog.tower_view_timeout)
        self.cog = cog
        self.progress = copy.deepcopy(progress)
        self.message: discord.Message | None = None
        self.add_item(JuiceBattleTowerChallengeButton())
        if int(self.progress.get("floor", cog.tower_floor_min)) > cog.tower_floor_min:
            self.add_item(JuiceBattleTowerEscapeButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        只允許爬塔隊員操作樓層介面。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "是否允許操作"
        """
        member_ids = {str(member_id) for member_id in self.progress.get("member_ids") or []}
        if await self.cog.tower_reject_if_aborted(interaction, member_ids):
            return False
        if str(interaction.user.id) in member_ids:
            return True
        await interaction.response.send_message(
            embed=Embed(title="Juice Battle｜爬塔", description="只有本層爬塔隊員可以操作。", color=common.bot_error_color),
            ephemeral=True,
        )
        return False

    async def on_challenge(self, interaction: discord.Interaction):
        """
        將樓層入口切換成爬塔戰鬥。

        Args:
            interaction (discord.Interaction): "挑戰按鈕互動"
        """
        await self.cog.tower_start_battle(interaction, self.progress)
        self.stop()

    async def on_escape(self, interaction: discord.Interaction):
        """
        結束爬塔並處理暫存獎勵。

        Args:
            interaction (discord.Interaction): "逃跑按鈕互動"
        """
        await self.cog.tower_escape(interaction, self.progress)
        self.stop()

    async def on_timeout(self) -> None:
        """
        樓層介面逾時後解除進行中鎖定，但保留進度供下次續爬。
        """
        for member_id in self.progress.get("member_ids") or []:
            await self.cog.clear_session(str(member_id))
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                embed = self.cog.tower_floor_embed(self.progress, log_text="操作逾時，請重新使用指令繼續。")
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


class JuiceBattleTowerNextFloorButton(discord.ui.Button):
    """前往下一層按鈕。"""

    def __init__(self):
        """建立前往下一層按鈕。"""
        super().__init__(label="前往下一層", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        """
        進入下一層樓層入口。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerNextFloorView = self.view  # type: ignore[assignment]
        await view.on_next_floor(interaction)


class JuiceBattleTowerNextFloorView(discord.ui.View):
    """爬塔單層通關後的戰鬥結果介面。"""

    def __init__(self, *, cog: JuiceBattle, progress: dict):
        """
        建立單層通關結果 View。

        Args:
            cog (JuiceBattle): "Juice Battle cog"
            progress (dict): "已保存下一層進度"
        """
        super().__init__(timeout=cog.tower_view_timeout)
        self.cog = cog
        self.progress = copy.deepcopy(progress)
        self.message: discord.Message | None = None
        self.finished = False
        self.add_item(JuiceBattleTowerNextFloorButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        只允許爬塔隊員進入下一層。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "是否為本次爬塔隊員"
        """
        member_ids = {str(member_id) for member_id in self.progress.get("member_ids") or []}
        if await self.cog.tower_reject_if_aborted(interaction, member_ids):
            return False
        if str(interaction.user.id) in member_ids:
            return True
        await interaction.response.send_message(
            embed=Embed(
                title="Juice Battle｜爬塔",
                description="只有本次爬塔隊員可以進入下一層。",
                color=common.bot_error_color,
            ),
            ephemeral=True,
        )
        return False

    async def on_next_floor(self, interaction: discord.Interaction):
        """
        顯示下一層怪物與挑戰／逃跑按鈕。

        Args:
            interaction (discord.Interaction): "前往下一層按鈕互動"
        """
        if self.finished:
            return
        self.finished = True
        next_view = JuiceBattleTowerFloorView(cog=self.cog, progress=self.progress)
        next_view.message = self.message
        await interaction.response.edit_message(
            embed=self.cog.tower_floor_embed(self.progress),
            view=next_view,
        )
        self.stop()

    async def on_timeout(self) -> None:
        """
        通關結果介面逾時後保存進度並解除隊伍鎖定。
        """
        if self.finished:
            return
        self.finished = True
        for member_id in self.progress.get("member_ids") or []:
            await self.cog.clear_session(str(member_id))
        floor_view = JuiceBattleTowerFloorView(cog=self.cog, progress=self.progress)
        for child in floor_view.children:
            child.disabled = True
        floor_view.message = self.message
        if self.message is not None:
            try:
                await self.message.edit(
                    embed=self.cog.tower_floor_embed(
                        self.progress,
                        log_text="通關結果介面操作逾時，請重新使用指令繼續。",
                    ),
                    view=floor_view,
                )
            except Exception:
                pass
        self.stop()


class JuiceBattleTowerAttackButton(discord.ui.Button):
    """爬塔玩家攻擊按鈕。"""

    def __init__(self):
        """建立攻擊按鈕。"""
        super().__init__(label="攻擊", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        """
        執行爬塔玩家攻擊。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerView = self.view  # type: ignore[assignment]
        await view.on_attack(interaction)


class JuiceBattleTowerDefendButton(discord.ui.Button):
    """爬塔玩家防禦按鈕。"""

    def __init__(self):
        """建立防禦按鈕。"""
        super().__init__(label="防禦", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        """
        執行爬塔玩家防禦。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerView = self.view  # type: ignore[assignment]
        await view.on_defend(interaction)


class JuiceBattleTowerDodgeButton(discord.ui.Button):
    """爬塔玩家閃避按鈕。"""

    def __init__(self):
        """建立閃避按鈕。"""
        super().__init__(label="閃避", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        """
        執行爬塔玩家閃避。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerView = self.view  # type: ignore[assignment]
        await view.on_dodge(interaction)


class JuiceBattleTowerSkillButton(discord.ui.Button):
    """爬塔角色、武器或防具技能按鈕。"""

    def __init__(self, *, source: str, label: str, armed: bool):
        """
        建立技能按鈕。

        Args:
            source (str): "技能來源"
            label (str): "按鈕顯示文字"
            armed (bool): "是否已發動"
        """
        display = f"{label}（已發動）" if armed else label
        super().__init__(label=display, style=discord.ButtonStyle.success)
        self.source = source

    async def callback(self, interaction: discord.Interaction):
        """
        發動或取消爬塔技能。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerView = self.view  # type: ignore[assignment]
        await view.on_skill(interaction, self.source)


class JuiceBattleTowerView(discord.ui.View):
    """多人爬塔的隊伍回合戰鬥介面。"""

    def __init__(self, *, cog: JuiceBattle, progress: dict, fighters: list[dict], monster: dict):
        """
        建立爬塔戰鬥 View。

        Args:
            cog (JuiceBattle): "Juice Battle cog"
            progress (dict): "爬塔快照"
            fighters (list[dict]): "玩家戰鬥角色"
            monster (dict): "怪物戰鬥角色"
        """
        super().__init__(timeout=cog.tower_view_timeout)
        self.cog = cog
        self.progress = copy.deepcopy(progress)
        self.fighters = fighters
        self.monster = monster
        self.monster_turn_id = "__tower_monster__"
        if self.monster.get("id") == "old_jin":
            for fighter in self.fighters:
                fighter["two_dice"] = True
        self.member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
        self.turn_order: list[str] = []
        self.current_index = 0
        self.round_number = 1
        self.phase = "player_attack"
        self.current_actor_id: str | None = None
        self.pending_target_id: str | None = None
        self.pending_attack_total: int | None = None
        self.pending_attack_dice = ""
        self.pending_bind = False
        self.last_attack_damage = 0
        self.log_text = ""
        self.finished = False
        self.message: discord.Message | None = None
        self.rebuild_buttons()

    def fighter_by_id(self, user_id: str) -> dict | None:
        """
        依 ID 取得隊員戰鬥狀態。

        Args:
            user_id (str): "玩家或怪物 ID"

        Returns:
            fighter (dict | None): "找到的隊員"
        """
        for fighter in self.fighters:
            if str(fighter["user_id"]) == str(user_id):
                return fighter
        return None

    def append_log(self, text: str):
        """
        將爬塔戰鬥紀錄接到目前紀錄後方。

        Args:
            text (str): "一行戰鬥紀錄"
        """
        if self.log_text:
            self.log_text = f"{self.log_text}\n{text}"
        else:
            self.log_text = text
        self.log_text = self.log_text[-3500:]

    def current_actor(self) -> dict | None:
        """
        取得目前等待操作的玩家。

        Returns:
            fighter (dict | None): "目前玩家"
        """
        if self.current_actor_id is None:
            return None
        return self.fighter_by_id(self.current_actor_id)

    def living_fighters(self) -> list[dict]:
        """
        取得目前仍存活的隊員。

        Returns:
            fighters (list[dict]): "HP 大於 0 的隊員"
        """
        return [fighter for fighter in self.fighters if fighter["hp"] > 0]

    def battle_snapshot(self) -> dict:
        """
        建立可寫入 MongoDB 的完整戰鬥快照。

        Returns:
            battle (dict): "玩家、怪物、回合與待處理攻防狀態"
        """
        return {
            "fighters": copy.deepcopy(self.fighters),
            "monster": copy.deepcopy(self.monster),
            "turn_order": list(self.turn_order),
            "current_index": self.current_index,
            "round_number": self.round_number,
            "phase": self.phase,
            "current_actor_id": self.current_actor_id,
            "pending_target_id": self.pending_target_id,
            "pending_attack_total": self.pending_attack_total,
            "pending_attack_dice": self.pending_attack_dice,
            "pending_bind": self.pending_bind,
            "last_attack_damage": self.last_attack_damage,
            "log_text": self.log_text,
        }

    async def save_battle_state(self):
        """
        將目前爬塔戰鬥快照同步保存給所有隊員。
        """
        await self.cog.tower_save_battle(self)

    def build_embed(self) -> Embed:
        """
        依爬塔戰鬥狀態建立 embed。

        Returns:
            embed (Embed): "爬塔戰鬥資訊"
        """
        floor = int(self.progress.get("floor", 1))
        embed = Embed(
            title=f"Juice Battle｜爬塔第 {floor} 層",
            description=f"第 **{self.round_number}** 回合",
            color=common.bot_color,
        )
        monster_ability = self.monster.get("ability") if isinstance(self.monster.get("ability"), dict) else None
        monster_status = []
        if self.monster.get("stun_remaining", 0) > 0:
            monster_status.append("暈眩")
        if self.monster.get("hellfire_offset", 0) > 0:
            monster_status.append(f"業火攻擊偏移 +{self.monster['hellfire_offset']}")
        if self.monster.get("poison_remaining", 0) > 0:
            monster_status.append(f"中毒 {self.monster['poison_remaining']}")
        monster_text = (
            f"生命 **{self.monster['hp']}/{self.monster['max_hp']}**\n"
            f"攻擊 {self.monster['atk']}({self.monster.get('attack_offset', 0):+d})｜"
            f"防禦 {self.monster['defense']}｜敏捷 {self.monster['agi']}"
        )
        if monster_ability:
            monster_text += f"\n技能：{monster_ability.get('name', '被動')}"
        if monster_status:
            monster_text += f"\n狀態：{'／'.join(monster_status)}"
        embed.add_field(name=f"怪物｜{self.monster['name']}", value=monster_text, inline=False)
        for fighter in self.fighters:
            status = []
            if fighter.get("stun_remaining", 0) > 0:
                status.append("暈眩")
            if fighter.get("poison_remaining", 0) > 0:
                status.append(f"中毒 {fighter['poison_remaining']}")
            if fighter.get("berserk_triggered"):
                status.append("暴走")
            armed_source = fighter.get("tower_skill_armed")
            if armed_source:
                ability = self.cog.tower_skill_definition(fighter, armed_source)
                if ability:
                    status.append(f"已發動：{ability['name']}")
            status_text = f"\n狀態：{'／'.join(status)}" if status else ""
            embed.add_field(
                name=f"{fighter['display_name']}（{fighter['character_name']}）",
                value=(
                    f"HP **{fighter['hp']}/{fighter['max_hp']}**\n"
                    f"攻擊 {fighter['atk']}({fighter.get('atk_offset', 0) + fighter.get('berserk_offset', 0):+d})｜"
                    f"防禦 {fighter['defense']}({fighter.get('def_offset', 0):+d})｜"
                    f"敏捷 {fighter['agi']}({fighter.get('agi_offset', 0) + fighter.get('dodge_offset', 0):+d})"
                    f"{status_text}"
                ),
                inline=False,
            )
        if self.log_text:
            embed.add_field(name="戰鬥紀錄", value=self.log_text[:1024], inline=False)
        action_text = "本層已通關" if self.finished else "戰鬥處理中"
        if not self.finished and self.phase == "player_attack" and self.current_actor() is not None:
            actor = self.current_actor()
            action_text = f"輪到 **{actor['display_name']}** 攻擊"
            armed_source = actor.get("tower_skill_armed")
            if armed_source:
                ability = self.cog.tower_skill_definition(actor, armed_source)
                if ability:
                    action_text += f"\n已發動：**{ability['name']}**"
        elif not self.finished and self.phase == "player_defend" and self.pending_target_id:
            defender = self.fighter_by_id(self.pending_target_id)
            action_text = f"輪到 **{defender['display_name']}** 選擇防禦或閃避"
            if self.pending_bind:
                action_text = f"輪到 **{defender['display_name']}** 選擇防禦（被束縛，無法閃避）"
            armed_source = defender.get("tower_skill_armed")
            if armed_source:
                ability = self.cog.tower_skill_definition(defender, armed_source)
                if ability:
                    action_text += f"\n已發動：**{ability['name']}**"
        embed.add_field(name="行動", value=action_text, inline=False)
        return embed

    def rebuild_buttons(self):
        """
        依目前戰鬥階段重建爬塔操作按鈕。
        """
        self.clear_items()
        if self.finished:
            return
        if self.phase == "player_attack":
            actor = self.current_actor()
            if actor is None:
                return
            self.add_item(JuiceBattleTowerAttackButton())
            for source in ("character", "weapon"):
                ability = self.cog.tower_skill_definition(actor, source)
                if ability and self.cog.tower_skill_is_ready(actor, source, "attack"):
                    self.add_item(
                        JuiceBattleTowerSkillButton(
                            source=source,
                            label=f"{'角色' if source == 'character' else '武器'}：{ability['name']}",
                            armed=actor.get("tower_skill_armed") == source,
                        )
                    )
        elif self.phase == "player_defend":
            defender = self.fighter_by_id(self.pending_target_id or "")
            if defender is None:
                return
            self.add_item(JuiceBattleTowerDefendButton())
            life_conversion_armed = defender.get("tower_skill_armed") == "armor" and (
                self.cog.tower_skill_definition(defender, "armor") or {}
            ).get("id") == "life_conversion"
            if not self.pending_bind and not life_conversion_armed:
                self.add_item(JuiceBattleTowerDodgeButton())
            for source in ("character", "armor", "weapon"):
                ability = self.cog.tower_skill_definition(defender, source)
                if ability and self.cog.tower_skill_is_ready(defender, source, "defend"):
                    self.add_item(
                        JuiceBattleTowerSkillButton(
                            source=source,
                            label=(
                                f"{'角色' if source == 'character' else '防具' if source == 'armor' else '武器'}："
                                f"{ability['name']}"
                            ),
                            armed=defender.get("tower_skill_armed") == source,
                        )
                    )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        只允許目前回合的爬塔隊員操作。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "是否為目前行動者"
        """
        if self.finished:
            await interaction.response.send_message(
                embed=Embed(
                    title="Juice Battle",
                    description="此戰鬥已結束或已失效。",
                    color=common.bot_error_color,
                ),
                ephemeral=True,
            )
            return False
        if await self.cog.tower_reject_if_aborted(interaction, self.member_ids):
            return False
        actor = (
            self.current_actor()
            if self.phase == "player_attack"
            else self.fighter_by_id(self.pending_target_id or "")
        )
        if actor is None or str(interaction.user.id) != str(actor["user_id"]):
            await interaction.response.send_message(
                embed=Embed(
                    title="Juice Battle",
                    description="現在不是你的回合。",
                    color=common.bot_error_color,
                ),
                ephemeral=True,
            )
            return False
        return True

    async def begin(self):
        """
        擲玩家與怪物先攻骰並開始戰鬥。
        """
        while True:
            initiative = []
            for fighter in self.fighters:
                _dice, total, _dice_text = self.cog.tower_roll(
                    fighter,
                    fighter["agi"],
                    fighter.get("agi_offset", 0),
                )
                initiative.append((total, fighter["user_id"]))
            monster_total = self.cog.tower_roll(
                self.monster,
                self.monster["agi"],
                0,
            )[1]
            player_totals = [item[0] for item in initiative]
            if (
                len(initiative) <= 1
                or len(set(player_totals)) == len(player_totals)
            ) and monster_total != max(player_totals):
                break
        initiative.sort(key=lambda item: item[0], reverse=True)
        player_order = [str(user_id) for _total, user_id in initiative]
        if monster_total > initiative[0][0]:
            self.turn_order = [self.monster_turn_id] + player_order
        else:
            self.turn_order = player_order + [self.monster_turn_id]
        initiative_text = "｜".join(
            f"{self.fighter_by_id(user_id)['display_name']} 先攻 **{total}**"
            for total, user_id in initiative
        )
        initiative_text = (
            f"{initiative_text}｜{self.monster['name']} 先攻 **{monster_total}**"
        )
        first_name = self.monster["name"] if monster_total > initiative[0][0] else (
            self.fighter_by_id(initiative[0][1])["display_name"]
        )
        self.log_text = f"{initiative_text}\n**{first_name}** 先攻！"
        await self.enter_next_player()

    async def enter_next_player(self):
        """
        依先攻順序找到下一位玩家或切換到怪物回合。
        """
        while self.current_index < len(self.turn_order):
            user_id = self.turn_order[self.current_index]
            self.current_index += 1
            if user_id == self.monster_turn_id:
                await self.run_monster_turn()
                return
            fighter = self.fighter_by_id(user_id)
            if fighter is None or fighter["hp"] <= 0:
                continue
            self.current_actor_id = user_id
            self.phase = "player_attack"
            self.prepare_player_turn(fighter)
            if fighter["hp"] > 0 and fighter.get("stun_remaining", 0) <= 0:
                self.rebuild_buttons()
                if self.message is not None:
                    await self.message.edit(embed=self.build_embed(), view=self)
                await self.save_battle_state()
                return
            if fighter["hp"] <= 0:
                self.append_log(f"{fighter['display_name']} 因狀態傷害倒下。")
            else:
                self.append_log(f"{fighter['display_name']} 暈眩，跳過本次攻擊。")
            if fighter.get("stun_remaining", 0) > 0:
                fighter["stun_remaining"] = max(0, fighter["stun_remaining"] - 1)
        self.round_number += 1
        self.current_index = 0
        await self.enter_next_player()

    def prepare_player_turn(self, fighter: dict):
        """
        處理玩家攻擊回合開始時的 CD、中毒與暈眩狀態。

        Args:
            fighter (dict): "本回合玩家"
        """
        self.cog.tower_prepare_skill_cooldowns(fighter, "attack")
        fighter["tower_skill_armed"] = None
        fighter["dodge_offset"] = 0
        if int(fighter.get("poison_remaining", 0)) > 0:
            damage = self.apply_damage(fighter, 1)
            fighter["poison_remaining"] = max(0, int(fighter["poison_remaining"]) - 1)
            self.append_log(
                f"{fighter['display_name']} 中毒，受到 **{damage}** 點傷害（剩餘 {fighter['poison_remaining']} 回合）"
            )

    def apply_damage(self, target: dict, damage: int, *, count_damage: bool = True) -> int:
        """
        套用爬塔傷害並處理吸收、暴走與地獄業火重置。

        Args:
            target (dict): "受到傷害的角色"
            damage (int): "原始傷害"
            count_damage (bool): "是否計入狂戰鎧甲承受次數"

        Returns:
            actual_damage (int): "實際扣除的生命值"
        """
        damage = max(0, int(damage))
        armor_ability = target.get("armor_ability") if isinstance(target.get("armor_ability"), dict) else {}
        if damage == 1 and armor_ability.get("id") == "absorption":
            return 0
        if target.get("ghost_armed"):
            target["ghost_armed"] = False
            return 0
        actual_damage = min(damage, max(0, int(target.get("hp", 0))))
        target["hp"] = max(0, int(target.get("hp", 0)) - actual_damage)
        if actual_damage > 0 and count_damage:
            target["damage_taken_count"] = int(target.get("damage_taken_count", 0)) + 1
            if armor_ability.get("id") == "berserk" and target["damage_taken_count"] >= 5:
                target["berserk_triggered"] = True
                target["berserk_offset"] = 3
            if target.get("id") == "hell_wraith":
                target["hellfire_offset"] = 0
                target["attack_offset"] = 0
        return actual_damage

    def monster_skill_ready(self, phase: str) -> bool:
        """
        判斷目前怪物技能是否能在指定階段使用。

        Args:
            phase (str): "attack 或 defend"

        Returns:
            ready (bool): "是否可使用"
        """
        ability = self.monster.get("ability") if isinstance(self.monster.get("ability"), dict) else {}
        return ability.get("phase") == phase and int(self.monster.get("skill_cd", 0)) <= 0

    def monster_consume_skill(self):
        """
        消耗目前怪物的 CD 技能。
        """
        ability = self.monster.get("ability") if isinstance(self.monster.get("ability"), dict) else {}
        if ability.get("cd") is not None:
            self.monster["skill_cd"] = int(ability["cd"])

    def choose_monster_defense(self, attack_total: int, bound: bool) -> str:
        """
        依預期傷害選擇防禦或閃避（決策比照挑戰 Natalie）。

        Args:
            attack_total (int): "玩家攻擊總值"
            bound (bool): "是否被角色束縛"

        Returns:
            mode (str): "defend、dodge 或 stunned"
        """
        ability = self.monster.get("ability") if isinstance(self.monster.get("ability"), dict) else {}
        if self.monster.get("stun_remaining", 0) > 0:
            return "stunned"
        if bound:
            return "defend"
        # 大跑就緒時強制閃避（對應 Natalie 發動冰箱時選閃避）
        if self.monster_skill_ready("defend") and ability.get("id") == "sprint":
            self.monster["sprint_armed"] = True
            self.monster_consume_skill()
            return "dodge"
        if int(self.monster.get("hp", 0)) == 1:
            return "dodge"

        defense_base = int(self.monster.get("defense", 0))
        defend_damage_sum = 0
        for dice in range(1, 7):
            defense_total = dice + defense_base
            defend_damage_sum += max(1, attack_total - defense_total)
        defend_expected = defend_damage_sum / 6

        agility_base = int(self.monster.get("agi", 0)) + int(self.monster.get("dodge_offset", 0))
        dodge_damage_sum = 0
        for dice in range(1, 7):
            dodge_total = dice + agility_base
            if attack_total >= dodge_total:
                dodge_damage_sum += attack_total
        dodge_expected = dodge_damage_sum / 6

        if defend_expected < dodge_expected:
            return "defend"
        if dodge_expected < defend_expected:
            return "dodge"
        return random.choice(["defend", "dodge"])

    def resolve_player_attack(self, attacker: dict, *, use_dodge_roll: bool, bound: bool) -> str:
        """
        結算玩家對怪物的一次攻擊。

        Args:
            attacker (dict): "攻擊玩家"
            use_dodge_roll (bool): "是否用敏捷骰攻擊"
            bound (bool): "本次是否禁止怪物閃避"

        Returns:
            result (str): "攻擊結果文字"
        """
        if use_dodge_roll:
            _dice, attack_total, _dice_text = self.cog.tower_roll(
                attacker,
                attacker["agi"],
                attacker.get("agi_offset", 0),
            )
            attack_label = "閃避骰"
        else:
            base = attacker["defense"] if attacker.get("stance_swap_attack") else attacker["atk"]
            offset = attacker.get("def_offset", 0) if attacker.get("stance_swap_attack") else attacker.get("atk_offset", 0)
            offset += int(attacker.get("berserk_offset", 0))
            _dice, attack_total, _dice_text = self.cog.tower_roll(attacker, base, offset)
            attack_label = "攻擊"
        if attacker.get("stance_swap_attack"):
            attacker["stance_swap_attack"] = False
        mode = self.choose_monster_defense(attack_total, bound)
        if mode == "stunned":
            damage = self.apply_damage(self.monster, attack_total)
            self.last_attack_damage = damage
            self.monster["stun_remaining"] = max(0, int(self.monster.get("stun_remaining", 0)) - 1)
            result = (
                f"{attacker['display_name']} {attack_label} **{attack_total}**，"
                f"怪物暈眩，無法防禦，造成 **{damage}** 傷害"
            )
        elif mode == "defend":
            self.monster["sprint_armed"] = False
            _defense_dice, defense_total, defense_text = self.cog.tower_roll(
                self.monster,
                self.monster["defense"],
                0,
            )
            damage = max(1, attack_total - defense_total)
            ability = self.monster.get("ability") if isinstance(self.monster.get("ability"), dict) else {}
            hardening_text = ""
            if ability.get("id") == "hardened_shell" and self.monster_skill_ready("defend"):
                self.monster_consume_skill()
                if damage <= 3:
                    damage = 0
                    hardening_text = "，硬化甲殼使傷害無效"
            self.monster["hardening_armed"] = False
            actual_damage = self.apply_damage(self.monster, damage)
            self.last_attack_damage = actual_damage
            result = (
                f"{attacker['display_name']} {attack_label} **{attack_total}**，"
                f"怪物防禦 **{defense_total}**，受到 **{actual_damage}** 傷害{hardening_text}"
            )
        else:
            dodge_offset = int(self.monster.get("dodge_offset", 0))
            _dodge_dice, dodge_total, dodge_text = self.cog.tower_roll(
                self.monster,
                self.monster["agi"],
                dodge_offset,
                offset_multiplier=2 if self.monster.get("sprint_armed") else 1,
            )
            if attack_total >= dodge_total:
                damage = self.apply_damage(self.monster, attack_total)
                self.last_attack_damage = damage
                result = (
                    f"{attacker['display_name']} {attack_label} **{attack_total}**，"
                    f"怪物閃避 **{dodge_total}**，失敗，受到 **{damage}** 傷害"
                )
            else:
                self.last_attack_damage = 0
                result = (
                    f"{attacker['display_name']} {attack_label} **{attack_total}**，"
                    f"怪物閃避 **{dodge_total}**，成功，無傷"
                )
            self.monster["sprint_armed"] = False
        return result

    async def on_skill(self, interaction: discord.Interaction, source: str):
        """
        發動或取消目前玩家的爬塔技能。

        Args:
            interaction (discord.Interaction): "技能按鈕互動"
            source (str): "character、weapon 或 armor"
        """
        actor = self.current_actor() if self.phase == "player_attack" else self.fighter_by_id(self.pending_target_id or "")
        if actor is None:
            return
        phase = "attack" if self.phase == "player_attack" else "defend"
        ability = self.cog.tower_skill_definition(actor, source)
        if ability is None or ability.get("phase") != phase:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle｜爬塔", description="此階段無法使用這個技能。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        if actor.get("tower_skill_armed") == source:
            actor["tower_skill_armed"] = None
        else:
            if not self.cog.tower_skill_is_ready(actor, source, phase):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle｜爬塔", description="技能尚未準備好。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            actor["tower_skill_armed"] = source
        self.rebuild_buttons()
        await self.save_battle_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_attack(self, interaction: discord.Interaction):
        """
        結算目前玩家的一回合攻擊。

        Args:
            interaction (discord.Interaction): "攻擊按鈕互動"
        """
        await interaction.response.defer()
        attacker = self.current_actor()
        if attacker is None:
            return
        armed_source = attacker.get("tower_skill_armed")
        ability = self.cog.tower_consume_skill(attacker, armed_source) if armed_source else None
        attacker["tower_skill_armed"] = None
        attacker["pending_poison"] = False
        attack_count = 1
        second_attack_uses_dodge = False
        bind = False
        if ability:
            if ability["id"] == "starburst":
                attack_count = 2
                second_attack_uses_dodge = True
            elif ability["id"] == "bind":
                bind = True
            elif ability["id"] == "poison":
                attacker["pending_poison"] = True
            elif ability["id"] == "slime":
                self.monster["dodge_offset"] = int(self.monster.get("dodge_offset", 0)) - 1
            elif ability["id"] == "holy_light":
                for fighter in self.living_fighters():
                    self.cog.tower_add_hp(fighter, 3)
                self.append_log("聖光發動，所有存活隊員回復 **3 HP**。")
        armor_ability = attacker.get("armor_ability") if isinstance(attacker.get("armor_ability"), dict) else {}
        if armor_ability.get("id") == "desperate_counter" and attacker["hp"] in (1, 2):
            attack_count = max(attack_count, 3 if ability and ability.get("id") == "starburst" else 2)
            second_attack_uses_dodge = bool(ability and ability.get("id") == "starburst")
        results = []
        for attack_index in range(attack_count):
            result = self.resolve_player_attack(
                attacker,
                use_dodge_roll=second_attack_uses_dodge and attack_index > 0,
                bound=bind and attack_index == 0,
            )
            results.append(result)
            if self.monster["hp"] <= 0:
                break
            if attacker.get("pending_poison") and self.last_attack_damage > 0:
                if self.monster.get("id") != "poison_bubble_bug":
                    self.monster["poison_remaining"] = 3
                    results.append("怪物中毒（持續 3 回合）。")
                attacker["pending_poison"] = False
        attacker["pending_poison"] = False
        self.log_text = "\n".join(results)
        # 黏液只影響本次攻擊的閃避結算
        self.monster["dodge_offset"] = 0
        if self.monster["hp"] <= 0:
            await self.cog.tower_finish_floor(self, self.log_text)
            return
        self.phase = "resolving"
        self.rebuild_buttons()
        if self.message is not None:
            await self.message.edit(embed=self.build_embed(), view=self)
        await self.enter_next_player()

    async def run_monster_turn(self):
        """
        執行怪物回合並等待被選中隊員防禦或閃避。
        """
        living = self.living_fighters()
        if not living:
            await self.cog.tower_finish_defeat(self, "所有我方成員都已死亡。")
            return
        if int(self.monster.get("poison_remaining", 0)) > 0:
            poison_damage = self.apply_damage(self.monster, 1)
            self.monster["poison_remaining"] = max(0, int(self.monster["poison_remaining"]) - 1)
            self.append_log(
                f"{self.monster['name']} 中毒，受到 **{poison_damage}** 點傷害"
                f"（剩餘 {self.monster['poison_remaining']} 回合）"
            )
            if self.monster["hp"] <= 0:
                await self.cog.tower_finish_floor(self, self.log_text)
                return
        if self.monster.get("id") == "mushroom":
            self.cog.tower_add_hp(self.monster, 1)
            self.append_log("蘑菇的增值發動，怪物回復 **1 HP**。")
        if int(self.monster.get("skill_cd", 0)) > 0:
            self.monster["skill_cd"] = int(self.monster["skill_cd"]) - 1
        target = random.choice(living)
        self.pending_target_id = target["user_id"]
        ability = self.monster.get("ability") if isinstance(self.monster.get("ability"), dict) else {}
        self.pending_bind = False
        if ability.get("id") == "bind" and self.monster_skill_ready("attack"):
            self.monster_consume_skill()
            self.pending_bind = True
        _attack_dice, attack_total, attack_dice_text = self.cog.tower_roll(
            self.monster,
            self.monster["atk"],
            self.monster.get("attack_offset", 0),
        )
        self.pending_attack_total = attack_total
        self.pending_attack_dice = attack_dice_text
        self.phase = "player_defend"
        # 對齊挑戰玩家：進入防守階段時防守技能 CD-1
        self.cog.tower_prepare_skill_cooldowns(target, "defend")
        target["tower_skill_armed"] = None
        if self.monster.get("id") == "hell_wraith":
            self.monster["hellfire_offset"] = int(self.monster.get("hellfire_offset", 0)) + 1
            self.monster["attack_offset"] = self.monster["hellfire_offset"]
        skill_note = f"（發動 {ability['name']}）" if self.pending_bind else ""
        self.append_log(f"{self.monster['name']} 攻擊 **{attack_total}**{skill_note}")
        self.rebuild_buttons()
        if self.message is not None:
            await self.message.edit(embed=self.build_embed(), view=self)
        await self.save_battle_state()

    async def resolve_player_defense(self, mode: str, interaction: discord.Interaction):
        """
        結算被怪物選中的玩家防禦或閃避。

        Args:
            mode (str): "defend 或 dodge"
            interaction (discord.Interaction): "防守按鈕互動"
        """
        defender = self.fighter_by_id(self.pending_target_id or "")
        if defender is None or self.pending_attack_total is None:
            return
        if mode == "dodge" and self.pending_bind:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle｜爬塔", description="你被束縛，無法閃避。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        armed_source = defender.get("tower_skill_armed")
        ability = self.cog.tower_consume_skill(defender, armed_source) if armed_source else None
        defender["tower_skill_armed"] = None
        attack_total = int(self.pending_attack_total)
        damage = 0
        defender_skill_note = f"（發動 {ability['name']}）" if ability else ""
        monster_ability = self.monster.get("ability") if isinstance(self.monster.get("ability"), dict) else {}
        monster_skill_note = f"（發動 {monster_ability['name']}）" if self.pending_bind else ""
        log_parts = [f"{self.monster['name']} 攻擊 **{attack_total}**{monster_skill_note}"]
        defense_dice = 0
        defense_total = 0
        if mode == "dodge":
            defense_dice, dodge_total, _dodge_text = self.cog.tower_roll(
                defender,
                defender["agi"],
                defender.get("agi_offset", 0) + defender.get("dodge_offset", 0),
            )
            if attack_total >= dodge_total:
                damage = attack_total
                log_parts.append(
                    f"{defender['display_name']} 閃避 **{dodge_total}**{defender_skill_note}，失敗"
                )
            else:
                log_parts.append(
                    f"{defender['display_name']} 閃避 **{dodge_total}**{defender_skill_note}，成功，無傷"
                )
        else:
            stance_swap = bool(ability and ability.get("id") == "stance_swap")
            if stance_swap:
                defense_base = defender["atk"]
                defense_offset = defender.get("atk_offset", 0)
            else:
                defense_base = defender["defense"]
                defense_offset = defender.get("def_offset", 0)
            defense_dice, defense_total, _defense_text = self.cog.tower_roll(
                defender,
                defense_base,
                defense_offset,
            )
            if ability and ability.get("id") == "life_conversion":
                damage = attack_total
            else:
                damage = max(1, attack_total - defense_total)
            log_parts.append(f"{defender['display_name']} 防禦 **{defense_total}**{defender_skill_note}")
            if ability and ability.get("id") == "shield_counter" and defense_total == attack_total:
                self.monster["stun_remaining"] = 1
                log_parts.append("盾反成功，怪物暈眩一回合")
            if stance_swap:
                defender["stance_swap_attack"] = True
        trap = self.monster.get("ability") if isinstance(self.monster.get("ability"), dict) else {}
        trap_triggered = trap.get("id") == "trap" and defense_dice == 1
        if trap_triggered:
            damage = attack_total
            defender["stun_remaining"] = 1
            log_parts.append("捕獸夾骰出 1，暈眩生效並吃滿傷害")

        # 冰箱：致死傷害無效並改為等量回復（與挑戰玩家相同）
        fridge_armed = bool(ability and ability.get("id") == "fridge")
        if fridge_armed and damage > 0 and int(defender["hp"]) - damage <= 0:
            heal = damage
            defender["hp"] = min(int(defender["max_hp"]), int(defender["hp"]) + heal)
            log_parts.append(f"{defender['display_name']} 冰箱發動！傷害無效，回復 **{heal}** 點生命")
            actual_damage = 0
        else:
            ghost = bool(ability and ability.get("id") == "ghost")
            if ghost:
                defender["ghost_armed"] = True
            actual_damage = self.apply_damage(defender, damage)
            if ghost:
                log_parts.append("幽靈化發動，傷害無效")
            else:
                log_parts.append(f"受到 **{actual_damage}** 點傷害")

        if ability and ability.get("id") == "life_conversion" and defender["hp"] > 0:
            self.cog.tower_add_hp(defender, defense_total)
            log_parts.append(f"生命轉換回復 **{defense_total} HP**")
        # 反傷需發動荊棘盔甲技能，不是穿著就觸發
        if ability and ability.get("id") == "thorn" and actual_damage > 0 and defender["hp"] > 0:
            reflect = actual_damage // 2
            reflected = self.apply_damage(self.monster, reflect)
            log_parts.append(f"反傷造成 **{reflected}** 點傷害")
        # 黏呼呼：造成傷害後才上閃避減益，持續到該玩家下次攻擊回合
        if (
            self.monster.get("id") == "sticky_slime"
            and actual_damage > 0
            and defender["hp"] > 0
        ):
            defender["dodge_offset"] = -1
            log_parts.append(f"{defender['display_name']} 被黏液黏住，閃避偏移 -1")
        self.log_text = "\n".join(log_parts)
        self.pending_attack_total = None
        self.pending_attack_dice = ""
        self.pending_bind = False
        if not self.living_fighters():
            await self.cog.tower_finish_defeat(self, "所有我方成員都已死亡。")
            return
        if self.monster["hp"] <= 0:
            await self.cog.tower_finish_floor(self, self.log_text)
            return
        await self.enter_next_player()
        if interaction.response.is_done():
            return
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_defend(self, interaction: discord.Interaction):
        """
        玩家選擇防禦。

        Args:
            interaction (discord.Interaction): "防禦按鈕互動"
        """
        await interaction.response.defer()
        await self.resolve_player_defense("defend", interaction)

    async def on_dodge(self, interaction: discord.Interaction):
        """
        玩家選擇閃避。

        Args:
            interaction (discord.Interaction): "閃避按鈕互動"
        """
        if self.pending_bind:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle｜爬塔", description="你被束縛，無法閃避。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        await self.resolve_player_defense("dodge", interaction)

    async def on_timeout(self) -> None:
        """
        戰鬥操作逾時時保留樓層進度，解除隊伍的進行中鎖定。
        """
        if self.finished:
            return
        self.finished = True
        await self.save_battle_state()
        self.rebuild_buttons()

        # 清除本場戰鬥鎖定，但保留已保存的樓層、戰利品與進度。
        for member_id in self.member_ids:
            await self.cog.clear_session(member_id)

        if self.message is not None:
            try:
                embed = self.build_embed()
                embed.description = "戰鬥操作逾時，已保存本場戰鬥狀態；請重新使用指令繼續。"
                await self.message.edit(
                    embed=embed,
                    view=None,
                )
            except Exception:
                pass
        self.stop()


class JuiceBattleTowerClaimButton(discord.ui.Button):
    """爬塔裝備領取者按鈕。"""

    def __init__(self, *, member_id: str, label: str):
        """
        建立裝備領取者按鈕。

        Args:
            member_id (str): "領取者 ID"
            label (str): "按鈕顯示文字"
        """
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.member_id = member_id

    async def callback(self, interaction: discord.Interaction):
        """
        指定目前裝備的領取者。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerRewardView = self.view  # type: ignore[assignment]
        await view.on_claim(interaction, self.member_id)


class JuiceBattleTowerRewardView(discord.ui.View):
    """雙人爬塔的裝備領取介面。"""

    def __init__(self, *, cog: JuiceBattle, progress: dict, pending_index: int, recipients: list[str]):
        """
        建立裝備領取 View。

        Args:
            cog (JuiceBattle): "Juice Battle cog"
            progress (dict): "爬塔快照"
            pending_index (int): "目前處理的裝備索引"
            recipients (list[str]): "已指定的領取者"
        """
        super().__init__(timeout=cog.tower_view_timeout)
        self.cog = cog
        self.progress = copy.deepcopy(progress)
        self.pending_index = pending_index
        self.recipients = list(recipients)
        self.message: discord.Message | None = None
        self.claimed = False
        self.rebuild_buttons()

    def item_name(self) -> str:
        """
        取得目前待領取裝備名稱。

        Returns:
            name (str): "裝備名稱"
        """
        pending = self.progress.get("pending_equipment") or []
        if self.pending_index < 0 or self.pending_index >= len(pending):
            return "未知裝備"
        item_id = pending[self.pending_index]
        template = self.cog.item_template("weapon", item_id) or self.cog.item_template("armor", item_id)
        return template["name"] if template else str(item_id)

    def build_embed(self) -> Embed:
        """
        建立裝備領取選擇 embed。

        Returns:
            embed (Embed): "裝備領取資訊"
        """
        total = len(self.progress.get("pending_equipment") or [])
        current = min(self.pending_index + 1, max(total, 1))
        return Embed(
            title="Juice Battle｜領取爬塔裝備",
            description=(
                f"請指定第 **{current}/{total}** 件裝備的領取者：**{self.item_name()}**。\n"
                f"蛋糕：**{int(self.progress.get('pending_cake', 0))}** {common.cake_emoji}"
            ),
            color=common.bot_color,
        )

    def rebuild_buttons(self):
        """
        依隊員重建裝備領取按鈕。
        """
        self.clear_items()
        names = self.progress.get("member_names") if isinstance(self.progress.get("member_names"), dict) else {}
        for member_id in self.progress.get("member_ids") or []:
            label = str(names.get(str(member_id)) or member_id)
            self.add_item(JuiceBattleTowerClaimButton(member_id=str(member_id), label=f"{label}領取"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        只允許爬塔隊員指定裝備領取者。

        Args:
            interaction (discord.Interaction): "按鈕互動"

        Returns:
            allowed (bool): "是否允許操作"
        """
        if str(interaction.user.id) in {str(member_id) for member_id in self.progress.get("member_ids") or []}:
            if await self.cog.tower_reject_if_aborted(interaction, self.progress.get("member_ids") or []):
                return False
            return True
        await interaction.response.send_message(
            embed=Embed(title="Juice Battle｜爬塔", description="只有本次隊員可以指定裝備。", color=common.bot_error_color),
            ephemeral=True,
        )
        return False

    async def on_claim(self, interaction: discord.Interaction, recipient_id: str):
        """
        記錄一件裝備的領取者，並進入下一件或結算。

        Args:
            interaction (discord.Interaction): "領取按鈕互動"
            recipient_id (str): "指定領取者 ID"
        """
        if self.claimed:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle｜爬塔", description="這件裝備已經有人指定領取。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        self.claimed = True
        self.recipients.append(str(recipient_id))
        total = len(self.progress.get("pending_equipment") or [])
        if self.pending_index + 1 < total:
            next_view = JuiceBattleTowerRewardView(
                cog=self.cog,
                progress=self.progress,
                pending_index=self.pending_index + 1,
                recipients=self.recipients,
            )
            next_view.message = self.message
            await interaction.response.edit_message(embed=next_view.build_embed(), view=next_view)
            self.stop()
            return
        await self.cog.tower_grant_rewards(self.progress, self.recipients)
        await interaction.response.edit_message(
            embed=Embed(
                title="Juice Battle｜爬塔結算",
                description=(
                    f"已成功逃跑並取得 **{int(self.progress.get('pending_cake', 0))}** {common.cake_emoji}。\n"
                    f"最高通關：第 **{int(self.progress.get('cleared_floor', 0))}** 層。\n"
                    "裝備已依選擇發放。"
                ),
                color=common.bot_color,
            ),
            view=None,
        )
        self.stop()

    async def on_timeout(self) -> None:
        """
        領取介面逾時時將未指定裝備交給隊伍第一位成員。
        """
        if self.claimed:
            return
        self.claimed = True
        member_ids = [str(member_id) for member_id in self.progress.get("member_ids") or []]
        while len(self.recipients) < len(self.progress.get("pending_equipment") or []):
            self.recipients.append(member_ids[0])
        await self.cog.tower_grant_rewards(self.progress, self.recipients)
        if self.message is not None:
            try:
                await self.message.edit(
                    embed=Embed(
                        title="Juice Battle｜爬塔結算",
                        description="領取操作逾時，未指定的裝備已交給隊伍發起者；蛋糕與最高樓層紀錄已結算。",
                        color=common.bot_color,
                    ),
                    view=None,
                )
            except Exception:
                pass


async def setup(client: commands.Bot):
    """
    載入 Juice Battle cog。

    Args:
        client (commands.Bot): "Natalie bot"
    """
    await client.add_cog(JuiceBattle(client))
