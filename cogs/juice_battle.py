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
        self.tower_view_timeout = 1200.0
        self.tower_button_unlock_delay = 1.0
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
        self.poison_duration = 3
        self.poison_base_damage = 1
        self.blood_feast_damage_per_stack = 1
        self.last_dance_hp_threshold = 5
        self.toxic_revival_heal = 1
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
                    "description": "本次攻擊成功時賦予中毒（首次：每跳 -1HP、持續 3 回合）；若對方已中毒，則剩餘回合疊加 3 且每跳傷害 +1",
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
            "iris": {
                "name": "伊莉絲",
                "hp": 13,
                "atk": 1,
                "defense": 1,
                "agi": 1,
                "ability": {
                    "id": "blood_rite",
                    "name": "祭血術",
                    "phase": "attack",
                    "cd": 5,
                    "description": "消耗當前HP÷3（向下取整）的生命，立即對對方造成消耗量×2傷害（跳過防守，可被吸收背心擋1）；不取代普攻。HP≤2無法發動。平衡:6",
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
            "iris_condemn_scythe": {
                "name": "伊莉絲的斷罪之鐮",
                "hp_offset": 3,
                "atk_offset": 0,
                "def_offset": -1,
                "agi_offset": 0,
                "ability": {
                    "id": "condemn",
                    "name": "斷罪",
                    "phase": "attack",
                    "cd": 1,
                    "description": "[被動]血色晚宴：每當自己受傷時獲得一層血宴。[攻擊階段(CD:1)]斷罪：消耗所有血宴，在本次攻擊後另外造成等同血宴層數的傷害（不可防禦或閃避）。",
                },
            },
            "lily_toxic_spear": {
                "name": "莉莉的毒棘槍",
                "hp_offset": 0,
                "atk_offset": 2,
                "def_offset": 1,
                "agi_offset": 2,
                "ability": {
                    "id": "toxic_spread",
                    "name": "毒性蔓延",
                    "phase": "passive",
                    "cd": None,
                    "description": "攻擊敵人時，若敵人身上有中毒效果，則最終攻擊值再加上等同中毒剩餘回合數的傷害，並延長一回合中毒狀態。",
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
            "iris_evening_gown": {
                "name": "伊莉絲的晚禮服",
                "hp_offset": 3,
                "atk_offset": 0,
                "def_offset": 1,
                "agi_offset": 1,
                "ability": {
                    "id": "last_dance",
                    "name": "最後一舞",
                    "phase": "passive",
                    "cd": None,
                    "description": "自身血量為 5 以下時，攻擊附帶吸血效果（回復等同本次造成的實際傷害）。",
                },
            },
            "lily_emerald_shawl": {
                "name": "莉莉的翠毒披肩",
                "hp_offset": 3,
                "atk_offset": 0,
                "def_offset": 2,
                "agi_offset": 1,
                "ability": {
                    "id": "toxic_revival",
                    "name": "毒性回生",
                    "phase": "passive",
                    "cd": None,
                    "description": "自身有中毒效果時，中毒跳傷轉變成回合開始時自身回復 1 HP（剩餘回合照常遞減）。",
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
                    "name": "增殖",
                    "description": "回合開始時回復 1 HP。",
                },
            },
            {"id": "spark", "name": "火花精", "ability": None},
            {"id": "fat_rat", "name": "肥滋滋老鼠", "ability": None},
            {"id": "troll", "name": "巨魔", "ability": None},
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
                    "description": "本回合只能閃避，閃避變為兩倍（閃避為 0 時不發動）。",
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
            {
                "id": "tribal_archer",
                "name": "部落弓箭手",
                "ability": {
                    "id": "poison",
                    "name": "中毒",
                    "description": "[被動]本次攻擊成功時，賦予對方中毒效果，對方回合開始時-1HP，持續3回合。",
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
            "poison_damage": 0,
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

    def tower_armed_sources(self, fighter: dict) -> list[str]:
        """
        取得目前已發動的技能來源清單（相容舊存檔的單一字串）。

        Args:
            fighter (dict): "玩家戰鬥狀態"

        Returns:
            sources (list): "['character', 'armor']"
        """
        armed = fighter.get("tower_skill_armed")
        if armed is None or armed == "":
            return []
        if isinstance(armed, str):
            return [armed]
        if isinstance(armed, list):
            return [str(source) for source in armed if source]
        return []

    def tower_is_skill_armed(self, fighter: dict, source: str) -> bool:
        """
        判斷指定來源技能是否已發動。

        Args:
            fighter (dict): "玩家戰鬥狀態"
            source (str): "character"

        Returns:
            armed (bool): "True"
        """
        return str(source) in self.tower_armed_sources(fighter)

    def tower_toggle_skill_armed(self, fighter: dict, source: str):
        """
        切換指定來源技能的發動狀態；可同時發動多個來源。

        Args:
            fighter (dict): "玩家戰鬥狀態"
            source (str): "armor"
        """
        sources = self.tower_armed_sources(fighter)
        source = str(source)
        if source in sources:
            sources = [item for item in sources if item != source]
        else:
            sources.append(source)
        fighter["tower_skill_armed"] = sources

    def tower_clear_skill_armed(self, fighter: dict):
        """
        清空已發動的技能來源。

        Args:
            fighter (dict): "玩家戰鬥狀態"
        """
        fighter["tower_skill_armed"] = []

    def tower_consume_armed_skills(self, fighter: dict) -> list[dict]:
        """
        消耗所有已發動技能並回傳技能定義清單。

        Args:
            fighter (dict): "玩家戰鬥狀態"

        Returns:
            abilities (list): "[{'id': 'fridge', 'name': '冰箱'}]"
        """
        abilities = []
        for source in self.tower_armed_sources(fighter):
            ability = self.tower_consume_skill(fighter, source)
            if ability is not None:
                abilities.append(ability)
        self.tower_clear_skill_armed(fighter)
        return abilities

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
        載入時清除殘留挑戰／爬塔介面鎖，並盡力把舊訊息標為作廢；有未結算賭注則退還。
        """
        collection = common.mongo_storage.get_collection("userdata")
        if collection is None:
            return
        cursor = collection.find(
            {
                "$or": [
                    {"juice_battle.playing": True},
                    {"juice_battle.tower_session": {"$type": "object"}},
                    {"juice_battle.session.tower": True},
                ]
            }
        )
        async for document in cursor:
            juice_battle = document.get("juice_battle") or {}
            user_id = str(document.get("_id"))
            # 挑戰 session 與爬塔 session 分開清；舊資料可能把爬塔寫在 session.tower
            sessions = []
            challenge_session = juice_battle.get("session")
            if isinstance(challenge_session, dict):
                sessions.append(challenge_session)
            tower_session = juice_battle.get("tower_session")
            if isinstance(tower_session, dict):
                sessions.append(tower_session)

            for session in sessions:
                channel_id = session.get("channel_id")
                message_id = session.get("message_id")

                # 重啟時退還尚未結算的 PvP 賭注（每位玩家退回自己那份）
                bet = int(session.get("bet", 0) or 0)
                is_challenge = not session.get("tower")
                if is_challenge and bet > 0 and not session.get("vs_bot") and not session.get("bet_settled"):
                    cake = int(document.get("cake", 0)) + bet
                    try:
                        await collection.update_one(
                            {"_id": user_id},
                            {"$set": {"cake": cake}},
                        )
                    except Exception:
                        pass

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
                    if is_challenge and bet > 0 and not session.get("vs_bot"):
                        description = (
                            f"機器人重啟，對戰已取消；賭注已退還（各 **{bet}** {common.cake_emoji}）。"
                            f"請重新使用指令哦。"
                        )
                    elif session.get("tower"):
                        description = "機器人重啟，爬塔介面已失效；進度仍保留，請重新使用指令繼續。"
                    else:
                        description = "機器人重啟，請重新使用指令哦。"
                    embed = Embed(
                        title="Juice Battle",
                        description=description,
                        color=common.bot_error_color,
                    )
                    await message.edit(embed=embed, view=None)
                except Exception:
                    pass
        await collection.update_many(
            {
                "$or": [
                    {"juice_battle.playing": True},
                    {"juice_battle.tower_session": {"$exists": True}},
                    {"juice_battle.session.tower": True},
                ]
            },
            {
                "$set": {"juice_battle.playing": False},
                "$unset": {
                    "juice_battle.session": "",
                    "juice_battle.tower_session": "",
                },
            },
        )
        # 自癒：清除「戰鬥快照全員已死」卻仍殘留的爬塔進度（逾時寫回造成）
        dead_cursor = collection.find(
            {"juice_battle.tower_progress.battle.fighters": {"$type": "array"}},
            {"_id": 1, "juice_battle.tower_progress": 1},
        )
        cleared_team_keys = set()
        async for document in dead_cursor:
            juice_battle = document.get("juice_battle") or {}
            progress = juice_battle.get("tower_progress")
            if not isinstance(progress, dict):
                continue
            battle = progress.get("battle")
            if not isinstance(battle, dict):
                continue
            fighters = battle.get("fighters")
            if not isinstance(fighters, list) or not fighters:
                continue
            if not all(int(fighter.get("hp", 0)) <= 0 for fighter in fighters if isinstance(fighter, dict)):
                continue
            member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
            team_key = self.tower_team_key(member_ids)
            if not team_key or team_key in cleared_team_keys:
                continue
            cleared_team_keys.add(team_key)
            await self.tower_clear_progress(list(team_key))

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
        # 舊版把爬塔介面寫在 playing/session.tower；遷移到獨立 tower_session
        session = juice_battle.get("session")
        if isinstance(session, dict) and session.get("tower"):
            if not isinstance(juice_battle.get("tower_session"), dict):
                juice_battle["tower_session"] = session
            juice_battle["playing"] = False
            juice_battle.pop("session", None)
        if juice_battle.get("tower_session") is not None and not isinstance(juice_battle.get("tower_session"), dict):
            juice_battle["tower_session"] = None
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

    def sort_juice_battle_bag(self, juice_battle: dict) -> None:
        """
        將背包相同裝備聚在一起（空格移到後方），並同步裝備中格子索引。

        相同定義：kind + item_id；同組內再依四項偏移排序，最後用原索引保持穩定。

        Args:
            juice_battle (dict): "{'bag': [], 'equipped_weapon_slot': 0}"
        """
        bag = juice_battle.get("bag")
        if not isinstance(bag, list) or not bag:
            return
        weapon_slot = juice_battle.get("equipped_weapon_slot")
        armor_slot = juice_battle.get("equipped_armor_slot")
        # 抽出非空格並組排序鍵
        occupied = []
        for index, entry in enumerate(bag):
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("kind") or "")
            item_id = str(entry.get("item_id") or "")
            kind_order = 0 if kind == "weapon" else 1 if kind == "armor" else 2
            offsets = self.equipment_stat_offsets(entry) or {}
            occupied.append(
                (
                    (
                        kind_order,
                        item_id,
                        int(offsets.get("hp_offset", 0)),
                        int(offsets.get("atk_offset", 0)),
                        int(offsets.get("def_offset", 0)),
                        int(offsets.get("agi_offset", 0)),
                        index,
                    ),
                    index,
                    entry,
                )
            )
        occupied.sort(key=lambda item: item[0])
        # 重組背包並重對裝備中索引
        new_bag = [None] * len(bag)
        new_weapon_slot = None
        new_armor_slot = None
        for new_index, (_, old_index, entry) in enumerate(occupied):
            new_bag[new_index] = entry
            if weapon_slot == old_index:
                new_weapon_slot = new_index
            if armor_slot == old_index:
                new_armor_slot = new_index
        juice_battle["bag"] = new_bag
        juice_battle["equipped_weapon_slot"] = new_weapon_slot
        juice_battle["equipped_armor_slot"] = new_armor_slot

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
        組出「仍在挑戰對戰中」的提示（含訊息連結）。

        Args:
            juice_battle (dict): "{'playing': True, 'session': {}}"

        Returns:
            text (str): "你還在對戰中。\\n對戰訊息：..."
        """
        url = self.session_jump_url(juice_battle.get("session"))
        if url:
            return f"你還在對戰中。\n對戰訊息：{url}"
        return "你還在對戰中。"

    def tower_session_block_description(self, juice_battle: dict) -> str:
        """
        組出「仍有進行中爬塔介面」的提示（含訊息連結）。

        Args:
            juice_battle (dict): "{'tower_session': {}}"

        Returns:
            text (str): "你還有進行中的爬塔介面。\\n爬塔訊息：..."
        """
        url = self.session_jump_url(juice_battle.get("tower_session"))
        if url:
            return f"你還有進行中的爬塔介面。\n爬塔訊息：{url}"
        return "你還有進行中的爬塔介面。"

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
            "poison_damage": 0,
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
            "tower_skill_armed": [],
            "damage_taken_count": 0,
            "berserk_triggered": False,
            "blood_feast_stacks": 0,
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

    def apply_poison(self, target: dict):
        """
        對目標施加中毒：首次為基準持續／每跳傷害；已有中毒則回合疊加且每跳傷害 +1。

        Args:
            target (dict): "{'poison_remaining': 0, 'poison_damage': 0}"
        """
        if int(target.get("poison_remaining", 0)) > 0:
            target["poison_remaining"] = int(target["poison_remaining"]) + self.poison_duration
            target["poison_damage"] = int(target.get("poison_damage", self.poison_base_damage)) + 1
            return
        target["poison_remaining"] = self.poison_duration
        target["poison_damage"] = self.poison_base_damage

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
        取得攻擊擲骰用的基礎值與偏移（大山架式只對調角色數值，不對調偏移）。

        Args:
            fighter (dict): "{'atk': 1, 'stance_swap_attack': True}"

        Returns:
            stats (tuple[int, int]): "(base, offset)"
        """
        berserk = int(fighter.get("berserk_offset", 0))
        if fighter.get("stance_swap_attack"):
            return fighter["defense"], fighter["atk_offset"] + berserk
        return fighter["atk"], fighter["atk_offset"] + berserk

    def defense_roll_stats(self, fighter: dict, *, stance_swap_defend: bool) -> tuple[int, int]:
        """
        取得防禦擲骰用的基礎值與偏移（大山架式只對調角色數值，不對調偏移）。

        Args:
            fighter (dict): "{'defense': 3}"
            stance_swap_defend (bool): "True"

        Returns:
            stats (tuple[int, int]): "(base, offset)"
        """
        if stance_swap_defend:
            return fighter["atk"], fighter["def_offset"]
        return fighter["defense"], fighter["def_offset"]

    def skill_source_label(self, source: str) -> str:
        """
        技能來源的按鈕前綴文案。

        Args:
            source (str): "character"

        Returns:
            label (str): "角色"
        """
        if source == "character":
            return "角色"
        if source == "armor":
            return "防具"
        return "武器"

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

    def multi_attack_plan(self, attacker: dict, ability_ids: set) -> list[dict]:
        """
        依星爆／絕地反擊決定本回合攻擊段數與各段擲骰方式（爬塔與挑戰共用）。

        Args:
            attacker (dict): "攻擊方戰鬥狀態"
            ability_ids (set): "{'starburst'}"

        Returns:
            plan (list[dict]): "[{'use_dodge_roll': False}, {'use_dodge_roll': True}]"
        """
        attack_count = 1
        if "starburst" in ability_ids:
            attack_count = 2
        armor_ability = attacker.get("armor_ability") if isinstance(attacker.get("armor_ability"), dict) else {}
        if armor_ability.get("id") == "desperate_counter" and attacker["hp"] in (1, 2):
            attack_count = max(attack_count, 3 if "starburst" in ability_ids else 2)
        return [
            {"use_dodge_roll": "starburst" in ability_ids and attack_index > 0}
            for attack_index in range(attack_count)
        ]

    def roll_attack(self, attacker: dict, *, use_dodge_roll: bool) -> tuple[int, int, str]:
        """
        結算一次攻擊擲骰（星爆第二段起用敏捷／閃避骰；爬塔與挑戰共用）。

        Args:
            attacker (dict): "攻擊方"
            use_dodge_roll (bool): "True 表示用敏捷骰攻擊"

        Returns:
            result (tuple[int, int, str]): "(dice, total, label) 例如 (5, 13, '閃避骰')"
        """
        if use_dodge_roll:
            dice, total, _text = self.tower_roll(
                attacker,
                attacker["agi"],
                attacker.get("agi_offset", 0),
            )
            return dice, total, "閃避骰"
        base, offset = self.attack_roll_stats(attacker)
        dice, total, _text = self.tower_roll(attacker, base, offset)
        return dice, total, "攻擊"

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
        清除指定玩家的挑戰對戰狀態（不影響爬塔進度／介面）。

        Args:
            userid (str): "4108"
        """
        user_data = await self.load_user(userid)
        user_data["juice_battle"]["playing"] = False
        user_data["juice_battle"].pop("session", None)
        await common.mongo_storage.replace_user(userid, user_data)

    async def clear_tower_session(self, userid: str):
        """
        清除指定玩家的爬塔介面鎖定（保留 tower_progress）。

        Args:
            userid (str): "4108"
        """
        user_data = await self.load_user(userid)
        user_data["juice_battle"].pop("tower_session", None)
        await common.mongo_storage.replace_user(userid, user_data)

    async def set_playing_session(self, userid: str, session: dict):
        """
        標記玩家進入挑戰對戰並寫入 session（不覆寫爬塔介面）。

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

    async def notify_challenge_dm(
        self,
        opponent: discord.Member,
        challenger: discord.abc.User,
        jump_url: str,
        bet: int = 0,
    ):
        """
        私訊被挑戰者，附上挑戰訊息連結。

        Args:
            opponent (discord.Member): "被挑戰者"
            challenger (discord.abc.User): "挑戰者"
            jump_url (str): "https://discord.com/channels/..."
            bet (int): "0"
        """
        description = (
            f"**{challenger.display_name}** 向你發起了 Juice Battle 挑戰！\n"
            f"請點擊下方連結回到挑戰訊息，並按下「同意挑戰」。"
        )
        if bet > 0:
            description += (
                f"\n賭注：各 **{bet}** {common.cake_emoji}"
                f"（同意後扣除，勝者獲得 **{bet * 2}**）"
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
        # 殘留的全員死亡戰鬥快照：視為已結束，清掉後不再開啟介面
        if view is None and isinstance(progress.get("battle"), dict):
            battle_fighters = progress["battle"].get("fighters")
            if (
                isinstance(battle_fighters, list)
                and battle_fighters
                and all(int(fighter.get("hp", 0)) <= 0 for fighter in battle_fighters if isinstance(fighter, dict))
            ):
                await self.tower_clear_progress(
                    [str(member_id) for member_id in progress.get("member_ids") or []]
                )
                embed = Embed(
                    title="Juice Battle｜爬塔",
                    description="偵測到已結束的殘留戰鬥資料，已自動清除；請重新開始爬塔。",
                    color=common.bot_error_color,
                )
                if edit_message:
                    await interaction.response.edit_message(embed=embed, view=None)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                return
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
        if isinstance(view, JuiceBattleTowerFloorView):
            self.schedule_tower_button_unlock(view)

    def schedule_tower_button_unlock(self, view: discord.ui.View):
        """
        排程解除爬塔按鈕鎖定，避免剛出現就誤觸。

        Args:
            view (discord.ui.View): "要解鎖的介面"
        """
        asyncio.create_task(self.unlock_tower_buttons_later(view))

    async def unlock_tower_buttons_later(self, view: discord.ui.View):
        """
        延遲後啟用 View 上的按鈕並刷新訊息。

        Args:
            view (discord.ui.View): "要解鎖的介面"
        """
        await asyncio.sleep(self.tower_button_unlock_delay)
        if view.is_finished():
            return
        for child in view.children:
            child.disabled = False
        message = getattr(view, "message", None)
        if message is None:
            return
        try:
            await message.edit(view=view)
        except Exception:
            return

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
        attacker = view.fighter_by_id(view.attacker_id) if view.phase in ("attack", "defend") else None
        slime_preview = False
        if attacker is not None and view.phase == "attack":
            slime_preview = any(
                (self.tower_skill_definition(attacker, source) or {}).get("id") == "slime"
                for source in self.tower_armed_sources(attacker)
            )
        for fighter in (view.fighter_a, view.fighter_b):
            armed_abilities = [
                ability
                for source in self.tower_armed_sources(fighter)
                for ability in [self.tower_skill_definition(fighter, source)]
                if ability is not None
            ]
            # 大山架式：只對調角色攻防數值，偏移量維持原欄位
            stance_active = bool(fighter.get("stance_swap_attack")) or any(
                ability.get("id") == "stance_swap" for ability in armed_abilities
            )
            if stance_active:
                display_atk = fighter["defense"]
                display_def = fighter["atk"]
            else:
                display_atk = fighter["atk"]
                display_def = fighter["defense"]
            display_atk_offset = int(fighter.get("atk_offset", 0)) + int(fighter.get("berserk_offset", 0))
            display_def_offset = int(fighter.get("def_offset", 0))
            display_agi_offset = int(fighter.get("agi_offset", 0)) + int(fighter.get("dodge_offset", 0))
            # 攻擊方已發動黏液時，預覽對手面板敏捷偏移 -1
            if (
                slime_preview
                and attacker is not None
                and fighter["user_id"] != attacker["user_id"]
            ):
                display_agi_offset -= 1

            status_parts = []
            if fighter.get("poison_remaining", 0) > 0:
                armor_ability = fighter.get("armor_ability") if isinstance(fighter.get("armor_ability"), dict) else {}
                if armor_ability.get("id") == "toxic_revival":
                    status_parts.append(f"毒性回生 {fighter['poison_remaining']}")
                else:
                    poison_damage = int(fighter.get("poison_damage", self.poison_base_damage))
                    status_parts.append(f"中毒({poison_damage}) {fighter['poison_remaining']}")
            if int(fighter.get("blood_feast_stacks", 0)) > 0:
                status_parts.append(f"血宴 {fighter['blood_feast_stacks']}")
            if fighter.get("stun_remaining", 0) > 0:
                status_parts.append("暈眩")
            if fighter.get("berserk_triggered"):
                status_parts.append("暴走")
            if int(fighter.get("dodge_offset", 0)) != 0:
                status_parts.append(f"黏液閃避偏移 {fighter['dodge_offset']:+d}")
            elif (
                slime_preview
                and attacker is not None
                and fighter["user_id"] != attacker["user_id"]
            ):
                status_parts.append("黏液閃避偏移 -1")
            if armed_abilities:
                names = "、".join(ability["name"] for ability in armed_abilities)
                status_parts.append(f"已發動：{names}")
            elif stance_active:
                status_parts.append("架式對調中")
            status_text = f"\n狀態：{'／'.join(status_parts)}" if status_parts else ""
            ability_names = []
            for source in ("character", "weapon", "armor"):
                ability = self.tower_skill_definition(fighter, source)
                if ability is not None:
                    ability_names.append(f"{self.skill_source_label(source)}：{ability['name']}")
            ability_text = f"\n技能：{'／'.join(ability_names)}" if ability_names else ""
            embed.add_field(
                name=f"{fighter['display_name']}（{fighter['character_name']}）",
                value=(
                    f"HP **{fighter['hp']}/{fighter['max_hp']}**\n"
                    f"攻擊 {display_atk}({display_atk_offset:+d})｜"
                    f"防禦 {display_def}({display_def_offset:+d})｜"
                    f"敏捷 {fighter['agi']}({display_agi_offset:+d})"
                    f"{ability_text}{status_text}"
                ),
                inline=False,
            )
        bet = int(getattr(view, "bet", 0) or 0)
        if bet > 0:
            bet_text = f"各 **{bet}** {common.cake_emoji}（勝者獲得 **{bet * 2}**）"
        else:
            bet_text = "無"
        embed.add_field(name="賭注", value=bet_text, inline=False)
        if view.log_text:
            embed.add_field(name="戰鬥紀錄", value=view.log_text[:1024], inline=False)
        if view.phase == "ended":
            embed.add_field(name="結果", value=view.result_text or "戰鬥結束", inline=False)
        elif view.phase == "attack":
            attacker = view.fighter_by_id(view.attacker_id)
            action = f"輪到 **{attacker['display_name']}** 攻擊"
            armed_abilities = [
                ability
                for source in self.tower_armed_sources(attacker)
                for ability in [self.tower_skill_definition(attacker, source)]
                if ability is not None
            ]
            if armed_abilities:
                names = "、".join(ability["name"] for ability in armed_abilities)
                action += f"\n已發動：**{names}**"
            embed.add_field(name="行動", value=action, inline=False)
        elif view.phase == "defend":
            defender = view.fighter_by_id(view.defender_id)
            if view.pending_bind:
                action = f"輪到 **{defender['display_name']}** 選擇防禦（被束縛，無法閃避）"
            else:
                action = f"輪到 **{defender['display_name']}** 選擇防禦或閃避"
            armed_abilities = [
                ability
                for source in self.tower_armed_sources(defender)
                for ability in [self.tower_skill_definition(defender, source)]
                if ability is not None
            ]
            if armed_abilities:
                names = "、".join(ability["name"] for ability in armed_abilities)
                action += f"\n已發動：**{names}**"
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
            # 對戰／爬塔進行中仍可更換；進行中狀態使用開局快照，不受影響
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
            # 對戰／爬塔進行中仍可調整裝備；進行中戰鬥使用快照
            await common.mongo_storage.replace_user(userid, user_data)
            embed = self.build_bag_embed(juice_battle, 0)
            view = JuiceBattleBagView(cog=self, userid=userid, page=0)
            await view.attach_slot_buttons(juice_battle)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="juice_battle", description="發起 Juice Battle 對戰")
    @app_commands.describe(
        opponent="要挑戰的玩家，或 Natalie",
        bet="賭注蛋糕數量（可選；雙方各出同等數量，勝者獲得合計）",
    )
    @app_commands.rename(opponent="對手", bet="賭注")
    async def juice_battle(
        self,
        interaction: discord.Interaction,
        opponent: discord.Member,
        bet: int | None = None,
    ):
        """
        挑戰玩家或 Natalie，開啟對戰／同意挑戰流程。

        Args:
            interaction (discord.Interaction): "slash 互動"
            opponent (discord.Member): "對手成員"
            bet (int | None): "100"
        """
        challenger = interaction.user
        challenger_id = str(challenger.id)
        opponent_id = str(opponent.id)
        stake = self.default_bet if bet is None else int(bet)

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
        if stake < 0:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="賭注不能為負數。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        if opponent.id == common.bot_id and stake > 0:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="挑戰 Natalie 無法設定賭注。", color=common.bot_error_color),
                ephemeral=True,
            )
            return

        async with common.jsonio_lock:
            challenger_data = await self.load_user(challenger_id)
            challenger_juice = challenger_data["juice_battle"]
            # 僅擋挑戰進行中；爬塔中（tower_session／tower_progress）仍可發起挑戰
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
            if stake > 0 and int(challenger_data.get("cake", 0)) < stake:
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle",
                        description=(
                            f"{common.cake_emoji}不足，無法設下賭注。"
                            f"（需要 **{stake}**，你只有 **{int(challenger_data.get('cake', 0))}**）"
                        ),
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
                    bet=0,
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
                        description=f"{opponent.display_name} 正在挑戰對戰中。",
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
                return
            await common.mongo_storage.replace_user(challenger_id, challenger_data)
            await common.mongo_storage.replace_user(opponent_id, opponent_data)

            if stake > 0:
                bet_line = (
                    f"賭注：各 **{stake}** {common.cake_emoji}"
                    f"（同意後扣除，勝者獲得 **{stake * 2}**）\n"
                )
            else:
                bet_line = f"賭注：無\n"
            embed = Embed(
                title="Juice Battle｜挑戰",
                description=(
                    f"{challenger.mention} 向 {opponent.mention} 發起挑戰！\n"
                    f"{bet_line}"
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
                bet=stake,
            )
            await interaction.response.send_message(embed=embed, view=view)
            message = await interaction.original_response()
            view.message = message
            jump_url = message.jump_url
            await self.notify_challenge_dm(opponent, challenger, jump_url, bet=stake)

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
            "member_loadouts": {},
        }

    def tower_capture_loadout(self, juice_battle: dict) -> dict:
        """
        擷取爬塔開局用的角色與裝備快照。

        Args:
            juice_battle (dict): "玩家 Juice Battle 資料"

        Returns:
            loadout (dict): "角色與裝備副本"
        """
        return {
            "character_id": juice_battle.get("character_id"),
            "bag": copy.deepcopy(juice_battle.get("bag") or []),
            "equipped_weapon_slot": juice_battle.get("equipped_weapon_slot"),
            "equipped_armor_slot": juice_battle.get("equipped_armor_slot"),
        }

    def tower_ensure_member_loadouts(self, progress: dict, user_data_map: dict[str, dict]):
        """
        確保爬塔進度有隊員開局快照；缺少時以目前資料補上一次。

        Args:
            progress (dict): "爬塔進度"
            user_data_map (dict[str, dict]): "隊員資料"
        """
        loadouts = progress.get("member_loadouts")
        if not isinstance(loadouts, dict):
            loadouts = {}
        member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
        changed = False
        for member_id in member_ids:
            if isinstance(loadouts.get(member_id), dict):
                continue
            user_data = user_data_map.get(member_id) or {}
            juice_battle = user_data.get("juice_battle") or {}
            loadouts[member_id] = self.tower_capture_loadout(juice_battle)
            changed = True
        if changed or progress.get("member_loadouts") is not loadouts:
            progress["member_loadouts"] = loadouts

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
        # 已正常結算（非逾時）或進度已被清掉時，禁止殘留 View 再寫回
        if view.finished and not view.timed_out:
            return
        if self.tower_is_aborted(view.member_ids):
            return
        existing = await self.tower_load_shared_progress(view.member_ids)
        if existing is None:
            return
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
        # 全員已死的快照不還原（避免已結算殘留被當成進行中）
        living = [
            fighter for fighter in fighters
            if isinstance(fighter, dict) and int(fighter.get("hp", 0)) > 0
        ]
        if fighters and not living:
            return None
        view = JuiceBattleTowerView(
            cog=self,
            progress=progress,
            fighters=copy.deepcopy(fighters),
            monster=copy.deepcopy(monster),
        )
        for fighter in view.fighters:
            fighter["tower_skill_armed"] = self.tower_armed_sources(fighter)
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
        標記爬塔隊伍的介面進行中（寫入 tower_session，不影響挑戰 playing）。

        Args:
            member_ids (list[str]): "隊伍成員 ID"
            session (dict): "爬塔訊息 session"
        """
        for member_id in member_ids:
            user_data = await self.load_user(str(member_id))
            user_data["juice_battle"]["tower_session"] = copy.deepcopy(session)
            await common.mongo_storage.replace_user(str(member_id), user_data)

    async def tower_clear_progress(self, member_ids: list[str]):
        """
        清除隊伍爬塔進度、暫存獎勵與爬塔介面鎖定（不影響進行中的挑戰）。

        Args:
            member_ids (list[str]): "隊伍成員 ID"
        """
        for member_id in member_ids:
            user_data = await self.load_user(str(member_id))
            juice_battle = user_data["juice_battle"]
            juice_battle.pop("tower_session", None)
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
                "juice_battle.tower_session": 1,
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
            # 自癒：全員已死的殘留戰鬥不當進行中，直接清掉
            battle = progress.get("battle") if isinstance(progress.get("battle"), dict) else None
            fighters = battle.get("fighters") if isinstance(battle, dict) else None
            if (
                isinstance(fighters, list)
                and fighters
                and all(int(fighter.get("hp", 0)) <= 0 for fighter in fighters if isinstance(fighter, dict))
            ):
                await self.tower_clear_progress(member_ids)
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
            tower_session = juice_battle.get("tower_session") if isinstance(juice_battle.get("tower_session"), dict) else None
            # 相容尚未遷移的舊 session.tower
            if tower_session is None:
                legacy_session = juice_battle.get("session") if isinstance(juice_battle.get("session"), dict) else {}
                if legacy_session.get("tower"):
                    tower_session = legacy_session
            runs_by_key[key] = {
                "team_key": ",".join(sorted(key)),
                "member_ids": member_ids,
                "members": members,
                "floor": int(progress.get("floor", self.tower_floor_min)),
                "cleared_floor": int(progress.get("cleared_floor", 0)),
                "monster_name": str(monster.get("name") or "未知怪物"),
                "playing": bool(tower_session),
                "session_url": self.session_jump_url(tower_session) if tower_session else None,
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
                current_session = user_data["juice_battle"].get("tower_session")
                if isinstance(current_session, dict):
                    session = current_session
                else:
                    # 相容尚未遷移的舊 session.tower
                    legacy_session = user_data["juice_battle"].get("session")
                    if isinstance(legacy_session, dict) and legacy_session.get("tower"):
                        session = legacy_session
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
        依爬塔進度建立本層玩家戰鬥狀態（使用開局角色／裝備快照）。

        Args:
            progress (dict): "目前爬塔快照"
            user_data_map (dict[str, dict]): "隊員 ID 對應使用者資料"

        Returns:
            fighters (list[dict]): "玩家戰鬥角色清單"
        """
        # 補齊舊進度缺少的開局快照，之後更換角色／裝備不影響本次爬塔
        self.tower_ensure_member_loadouts(progress, user_data_map)
        fighters = []
        member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
        saved_hp = progress.get("member_hp") if isinstance(progress.get("member_hp"), dict) else {}
        dead_ids = {str(member_id) for member_id in progress.get("dead_ids") or []}
        member_names = progress.setdefault("member_names", {})
        loadouts = progress.get("member_loadouts") if isinstance(progress.get("member_loadouts"), dict) else {}
        for member_id in member_ids:
            user_data = user_data_map[member_id]
            juice_battle = user_data["juice_battle"]
            loadout = loadouts.get(member_id) if isinstance(loadouts.get(member_id), dict) else None
            if loadout is not None:
                character_id = loadout.get("character_id") or juice_battle["character_id"]
                juice_for_fighter = {
                    "bag": loadout.get("bag") if isinstance(loadout.get("bag"), list) else juice_battle.get("bag"),
                    "equipped_weapon_slot": loadout.get("equipped_weapon_slot"),
                    "equipped_armor_slot": loadout.get("equipped_armor_slot"),
                }
            else:
                character_id = juice_battle["character_id"]
                juice_for_fighter = juice_battle
            display_name = str(member_names.get(member_id) or member_id)
            fighter = self.build_fighter(
                user_id=member_id,
                display_name=display_name,
                character_id=character_id,
                juice_battle=juice_for_fighter,
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

    async def tower_grant_rewards(self, progress: dict, recipient_ids: list[str | None]) -> dict:
        """
        將爬塔暫存獎勵發給隊員並寫入成功紀錄。

        Args:
            progress (dict): "成功逃跑的爬塔快照"
            recipient_ids (list[str | None]): "每件裝備的領取者 ID；None 表示已丟棄"

        Returns:
            bonus_report (dict): "{'base_cake': 1000, 'entries': [{'name': 'A', 'bonus': 200, 'sources': ['玉手鐲'], 'jade_text': '...'}]}"
        """
        member_ids = [str(member_id) for member_id in progress.get("member_ids") or []]
        member_names = progress.get("member_names") if isinstance(progress.get("member_names"), dict) else {}
        base_cake = int(progress.get("pending_cake", 0))
        house = getattr(self.bot, "server_item_house", None)
        bonus_entries = []
        user_data_map = {}
        for member_id in member_ids:
            user_data_map[member_id] = await self.load_user(member_id)
            # 玉手鐲／紫水晶項鍊：每位隊員依自己的 userdata 狀態分別加成（非隊長／共用）
            sources = []
            bonus = 0
            jade_text = ""
            if house is not None:
                if house.has_status_in_data(user_data_map[member_id], house.status_amethyst):
                    sources.append(house.status_labels[house.status_amethyst])
                if house.charge_remaining_in_data(user_data_map[member_id], house.status_jade_bracelet) > 0:
                    sources.append(house.status_labels[house.status_jade_bracelet])
                bonus = house.apply_win_cake_bonus(user_data_map[member_id], base_cake)
                # 成功逃跑視為完成一場遊戲，消耗玉手鐲場次
                if house.consume_charge_in_data(user_data_map[member_id], house.status_jade_bracelet):
                    leftover = house.charge_remaining_in_data(user_data_map[member_id], house.status_jade_bracelet)
                    jade_text = house.format_jade_bracelet_charge_text(leftover)
            user_data_map[member_id]["cake"] = int(user_data_map[member_id].get("cake", 0)) + base_cake + bonus
            if bonus > 0 or jade_text:
                bonus_entries.append(
                    {
                        "member_id": member_id,
                        "name": str(member_names.get(member_id) or member_id),
                        "bonus": bonus,
                        "sources": sources if bonus > 0 else [],
                        "jade_text": jade_text,
                    }
                )
        pending_equipment = [str(item_id) for item_id in progress.get("pending_equipment") or []]
        for item_id, recipient_id in zip(pending_equipment, recipient_ids):
            # 丟棄的裝備不發放
            if recipient_id is None:
                continue
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
        bonus_report = {"base_cake": base_cake, "entries": bonus_entries}
        # 與逾時 handler 共用鎖，避免結算清進度後又被寫回；並防止重複發放
        async with self.tower_lock:
            existing = await self.tower_load_shared_progress(member_ids)
            if existing is None:
                return {"base_cake": base_cake, "entries": []}
            for member_id, user_data in user_data_map.items():
                juice_battle = user_data["juice_battle"]
                # 發放後整理背包，讓相同裝備聚在一起
                self.sort_juice_battle_bag(juice_battle)
                juice_battle.pop("tower_session", None)
                juice_battle["tower_progress"] = None
                await common.mongo_storage.replace_user(member_id, user_data)
        await self.tower_record_success(progress)
        return bonus_report

    def tower_add_cake_bonus_fields(self, embed: Embed, bonus_report: dict | None):
        """
        在爬塔結算 embed 加上玉手鐲／紫水晶項鍊加成與消耗說明（無人吃到則省略）。

        Args:
            embed (Embed): "結算 embed"
            bonus_report (dict | None): "tower_grant_rewards 回傳"
        """
        if not isinstance(bonus_report, dict):
            return
        entries = bonus_report.get("entries") or []
        if not entries:
            return
        bonus_lines = []
        jade_lines = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            display_name = str(entry.get("name") or entry.get("member_id") or "?")
            bonus = int(entry.get("bonus") or 0)
            sources = [str(source) for source in entry.get("sources") or []]
            if bonus > 0:
                source_text = "＋".join(sources) if sources else "道具"
                bonus_lines.append(f"・**{display_name}**：{source_text} → **+{bonus}** {common.cake_emoji}")
            jade_text = str(entry.get("jade_text") or "")
            if jade_text:
                jade_lines.append(f"・**{display_name}**：{jade_text}")
        if bonus_lines:
            embed.add_field(name="道具加成", value="\n".join(bonus_lines), inline=False)
        if jade_lines:
            house = getattr(self.bot, "server_item_house", None)
            jade_name = house.status_labels[house.status_jade_bracelet] if house is not None else "玉手鐲"
            embed.add_field(name=jade_name, value="\n".join(jade_lines), inline=False)

    async def tower_finish_defeat(self, view: "JuiceBattleTowerView", reason: str):
        """
        清除全員死亡的爬塔進度。

        Args:
            view (JuiceBattleTowerView): "結束中的爬塔戰鬥 View"
            reason (str): "顯示給玩家的失敗原因"
        """
        async with self.tower_lock:
            if view.finished:
                return
            # 先標記結束並 stop，避免與 on_timeout 競態再寫回進度／舊畫面
            view.finished = True
            view.stop()
            await self.tower_clear_progress(view.member_ids)
        view.rebuild_buttons()
        if view.message is not None:
            try:
                await view.message.edit(
                    embed=Embed(
                        title="Juice Battle｜爬塔失敗",
                        description=f"{reason}\n本次爬塔的蛋糕、裝備與進度全部消失。",
                        color=common.bot_error_color,
                    ),
                    view=None,
                )
            except Exception:
                pass

    async def tower_finish_floor(self, view: "JuiceBattleTowerView", log_text: str):
        """
        結算一層爬塔戰鬥並顯示下一層入口。

        Args:
            view (JuiceBattleTowerView): "已擊敗怪物的爬塔戰鬥 View"
            log_text (str): "本層戰鬥紀錄"
        """
        async with self.tower_lock:
            if view.finished:
                return
            view.finished = True
            view.stop()
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
        # 無暫存裝備時直接結算蛋糕；有裝備時單／雙人皆進入領取介面
        if not pending_equipment:
            bonus_report = await self.tower_grant_rewards(progress, [])
            settle_embed = Embed(
                title="Juice Battle｜爬塔結算",
                description=(
                    f"已逃跑並取得 **{int(progress.get('pending_cake', 0))}** {common.cake_emoji}。\n"
                    f"最高通關：第 **{int(progress.get('cleared_floor', 0))}** 層。"
                ),
                color=common.bot_color,
            )
            self.tower_add_cake_bonus_fields(settle_embed, bonus_report)
            await interaction.response.edit_message(embed=settle_embed, view=None)
            return
        view = JuiceBattleTowerRewardView(cog=self, progress=progress, pending_index=0, recipients=[])
        view.message = interaction.message
        await interaction.response.edit_message(embed=view.build_embed(), view=view)
        self.schedule_tower_button_unlock(view)

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
            # 爬塔介面仍活著時請用原訊息，不可再開一份（與挑戰 playing 互不干擾）
            if isinstance(own_juice.get("tower_session"), dict):
                await interaction.response.send_message(
                    embed=Embed(
                        title="Juice Battle｜爬塔",
                        description=self.tower_session_block_description(own_juice),
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
                    member_juice = member_data["juice_battle"]
                    if isinstance(member_juice.get("tower_session"), dict):
                        await interaction.response.send_message(
                            embed=Embed(
                                title="Juice Battle｜爬塔",
                                description=f"<@{member_id}> 目前已有進行中的爬塔介面。",
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
            # 新開局寫入角色／裝備快照
            user_data_map = {str(member_id): await self.load_user(str(member_id)) for member_id in member_ids}
            self.tower_ensure_member_loadouts(progress, user_data_map)
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
            self.cog.sort_juice_battle_bag(juice_battle)
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

    def __init__(
        self,
        *,
        cog: JuiceBattle,
        challenger_id: str,
        opponent_id: str,
        challenger_name: str,
        opponent_name: str,
        bet: int = 0,
    ):
        super().__init__(timeout=cog.challenge_timeout)
        self.cog = cog
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.challenger_name = challenger_name
        self.opponent_name = opponent_name
        self.bet = max(0, int(bet))
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
                    embed=Embed(title="Juice Battle", description="其中一方已在挑戰對戰中，無法開始。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return

            # 有賭注時確認雙方蛋糕足夠並扣除
            if self.bet > 0:
                challenger_cake = int(challenger_data.get("cake", 0))
                opponent_cake = int(opponent_data.get("cake", 0))
                if challenger_cake < self.bet:
                    await interaction.response.send_message(
                        embed=Embed(
                            title="Juice Battle",
                            description=(
                                f"挑戰者 {common.cake_emoji}不足，無法開始。"
                                f"（需要 **{self.bet}**，目前 **{challenger_cake}**）"
                            ),
                            color=common.bot_error_color,
                        ),
                        ephemeral=True,
                    )
                    return
                if opponent_cake < self.bet:
                    await interaction.response.send_message(
                        embed=Embed(
                            title="Juice Battle",
                            description=(
                                f"你的 {common.cake_emoji}不足，無法同意這場賭注挑戰。"
                                f"（需要 **{self.bet}**，你只有 **{opponent_cake}**）"
                            ),
                            color=common.bot_error_color,
                        ),
                        ephemeral=True,
                    )
                    return
                challenger_data["cake"] = challenger_cake - self.bet
                opponent_data["cake"] = opponent_cake - self.bet
                await common.mongo_storage.replace_user(self.challenger_id, challenger_data)
                await common.mongo_storage.replace_user(self.opponent_id, opponent_data)

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
            bet=self.bet,
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
            "bet": self.bet,
            "bet_settled": False,
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
        if self.bet > 0:
            bet_line = f"\n賭注未扣除（各 **{self.bet}** {common.cake_emoji}）。"
        else:
            bet_line = ""
        embed = Embed(
            title="Juice Battle｜挑戰",
            description=(
                f"{self.challenger_name} 對 {self.opponent_name} 的挑戰已逾時取消。"
                f"{bet_line}"
            ),
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
    """角色／武器／防具技能按鈕（與爬塔共用來源標籤格式）。"""

    def __init__(self, *, source: str, label: str, armed: bool, disabled: bool = False):
        """
        建立挑戰戰技能按鈕。

        Args:
            source (str): "character、weapon 或 armor"
            label (str): "技能名稱"
            armed (bool): "是否已發動"
            disabled (bool): "是否鎖定（CD／已使用）"
        """
        display = f"{label}（已發動）" if armed else label
        super().__init__(label=display, style=discord.ButtonStyle.success, disabled=disabled)
        self.source = source

    async def callback(self, interaction: discord.Interaction):
        """
        發動或取消發動技能。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleView = self.view  # type: ignore[assignment]
        await view.on_skill(interaction, self.source)


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
        pending_condemn: int | None = None,
        result_text: str | None = None,
        bet: int = 0,
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
        self.pending_condemn = pending_condemn
        self.result_text = result_text
        self.bet = max(0, int(bet))
        self.bet_settled = False
        self.pending_extra_attacks: list[dict] = []
        self.attack_uses_dodge_roll = False
        self.resolving_followup = False
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
        self.cog.tower_prepare_skill_cooldowns(attacker, "attack")
        self.cog.tower_clear_skill_armed(attacker)

        # 中毒：攻擊階段開始時跳傷；翠毒披肩改為回復
        if int(attacker.get("poison_remaining", 0)) > 0:
            armor_ability = attacker.get("armor_ability") if isinstance(attacker.get("armor_ability"), dict) else {}
            if armor_ability.get("id") == "toxic_revival":
                before_hp = int(attacker.get("hp", 0))
                self.cog.tower_add_hp(attacker, self.cog.toxic_revival_heal)
                gained = int(attacker.get("hp", 0)) - before_hp
                attacker["poison_remaining"] = int(attacker["poison_remaining"]) - 1
                if attacker["poison_remaining"] <= 0:
                    attacker["poison_damage"] = 0
                self.append_log(
                    f"{attacker['display_name']} 毒性回生，回復 **{gained}** HP"
                    f"（剩餘 {attacker['poison_remaining']} 回合）"
                )
            else:
                tick_damage = int(attacker.get("poison_damage", self.cog.poison_base_damage))
                damage = self.apply_incoming_damage(attacker, tick_damage, count_damage=False)
                attacker["poison_remaining"] = int(attacker["poison_remaining"]) - 1
                if attacker["poison_remaining"] <= 0:
                    attacker["poison_damage"] = 0
                self.append_log(
                    f"{attacker['display_name']} 中毒，受到 **{damage}** 點傷害"
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
        self.cog.tower_prepare_skill_cooldowns(defender, "defend")
        self.cog.tower_clear_skill_armed(defender)

    def apply_incoming_damage(self, target: dict, damage: int, *, count_damage: bool = True) -> int:
        """
        套用傷害並處理吸收／幽靈化／暴走（與爬塔共用邏輯概念）。

        Args:
            target (dict): "受傷方"
            damage (int): "原始傷害"
            count_damage (bool): "是否計入狂戰鎧甲次數"

        Returns:
            actual_damage (int): "實際扣血"
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
        if actual_damage > 0:
            weapon_ability = target.get("weapon_ability") if isinstance(target.get("weapon_ability"), dict) else {}
            if weapon_ability.get("id") == "condemn":
                target["blood_feast_stacks"] = int(target.get("blood_feast_stacks", 0)) + 1
            if count_damage:
                target["damage_taken_count"] = int(target.get("damage_taken_count", 0)) + 1
                if armor_ability.get("id") == "berserk" and target["damage_taken_count"] >= 5:
                    target["berserk_triggered"] = True
                    target["berserk_offset"] = 3
        return actual_damage

    def rebuild_buttons(self):
        """
        依階段重建攻擊／防禦／閃避／技能按鈕（角色／武器／防具與爬塔一致）。
        """
        self.clear_items()
        if self.phase == "ended" or self.finished:
            return
        if self.phase == "attack":
            attacker = self.fighter_by_id(self.attacker_id)
            if attacker.get("is_bot"):
                return
            self.add_item(JuiceBattleAttackButton())
            for source in ("character", "weapon"):
                button = self.build_skill_button(attacker, source, "attack")
                if button is not None:
                    self.add_item(button)
            return
        if self.phase == "defend":
            defender = self.fighter_by_id(self.defender_id)
            if defender.get("is_bot"):
                return
            self.add_item(JuiceBattleDefendButton())
            life_conversion_armed = any(
                (self.cog.tower_skill_definition(defender, source) or {}).get("id") == "life_conversion"
                for source in self.cog.tower_armed_sources(defender)
            )
            if not self.pending_bind and not life_conversion_armed:
                self.add_item(JuiceBattleDodgeButton())
            for source in ("character", "armor", "weapon"):
                button = self.build_skill_button(defender, source, "defend")
                if button is not None:
                    self.add_item(button)

    def build_skill_button(self, fighter: dict, source: str, phase: str):
        """
        建立挑戰戰技能按鈕；標籤格式與爬塔相同（角色：中毒）。

        Args:
            fighter (dict): "目前行動的玩家"
            source (str): "character、weapon 或 armor"
            phase (str): "attack 或 defend"

        Returns:
            button (JuiceBattleSkillButton | None): "可顯示的技能按鈕"
        """
        ability = self.cog.tower_skill_definition(fighter, source)
        if ability is None or ability.get("phase") != phase:
            return None
        base_label = f"{self.cog.skill_source_label(source)}：{ability['name']}"
        armed = self.cog.tower_is_skill_armed(fighter, source)
        # 祭血術：HP≤2 或消耗 <1 時按鈕停用（不進 CD）
        blood_rite_blocked = False
        if ability.get("id") == "blood_rite":
            cost = int(fighter.get("hp", 0)) // 3
            blood_rite_blocked = int(fighter.get("hp", 0)) <= 2 or cost < 1
        if armed or self.cog.tower_skill_is_ready(fighter, source, phase):
            return JuiceBattleSkillButton(
                source=source,
                label=base_label,
                armed=armed,
                disabled=blood_rite_blocked and not armed,
            )
        if ability.get("cd") is None:
            if not fighter.get(f"{source}_skill_used"):
                return None
            return JuiceBattleSkillButton(
                source=source,
                label=f"{base_label}（已使用）",
                armed=False,
                disabled=True,
            )
        cd_left = int(fighter.get(f"{source}_skill_cd", 0))
        if cd_left <= 0:
            return None
        return JuiceBattleSkillButton(
            source=source,
            label=f"{base_label}（CD {cd_left}）",
            armed=False,
            disabled=True,
        )

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
            pending_condemn=self.pending_condemn,
            result_text=self.result_text,
            bet=self.bet,
        )
        new_view.message = self.message
        new_view.bet_settled = self.bet_settled
        new_view.pending_extra_attacks = list(self.pending_extra_attacks)
        new_view.attack_uses_dodge_roll = self.attack_uses_dodge_roll
        new_view.resolving_followup = self.resolving_followup
        embed = self.cog.build_battle_embed(new_view)
        if interaction is not None:
            await interaction.response.edit_message(embed=embed, view=new_view)
        elif self.message is not None:
            await self.message.edit(embed=embed, view=new_view)
        self.stop()
        return new_view

    async def finish_battle(self, *, winner: dict | None, reason: str, interaction: discord.Interaction | None):
        """
        結束挑戰戰鬥並清除雙方挑戰 playing；不影響爬塔進度／介面。有賭注時結算或退還蛋糕。

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

        # 結算賭注與清除挑戰對戰狀態（保留 tower_session／tower_progress）
        async with common.jsonio_lock:
            if winner is not None:
                loser = self.other_fighter(winner["user_id"])
                await self.cog.record_battle_outcome(winner, loser)
                if self.bet > 0 and not self.vs_bot and not self.bet_settled and not winner.get("is_bot"):
                    pot = self.bet * 2
                    winner_data = await self.cog.load_user(str(winner["user_id"]))
                    winner_data["cake"] = int(winner_data.get("cake", 0)) + pot
                    await common.mongo_storage.replace_user(str(winner["user_id"]), winner_data)
                    self.bet_settled = True
                    self.result_text += f"\n獲得賭注 **{pot}** {common.cake_emoji}"
            elif self.bet > 0 and not self.vs_bot and not self.bet_settled:
                for fighter in (self.fighter_a, self.fighter_b):
                    if fighter.get("is_bot"):
                        continue
                    fighter_data = await self.cog.load_user(str(fighter["user_id"]))
                    fighter_data["cake"] = int(fighter_data.get("cake", 0)) + self.bet
                    await common.mongo_storage.replace_user(str(fighter["user_id"]), fighter_data)
                self.bet_settled = True
                self.result_text += f"\n賭注已退還（各 **{self.bet}** {common.cake_emoji}）"
            await self.cog.clear_session(self.fighter_a["user_id"])
            if not self.fighter_b.get("is_bot"):
                await self.cog.clear_session(self.fighter_b["user_id"])

        self.rebuild_buttons()
        embed = self.cog.build_battle_embed(self)
        if interaction is not None and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=None)
        elif self.message is not None:
            await self.message.edit(embed=embed, view=None)
        self.stop()

    async def on_skill(self, interaction: discord.Interaction, source: str):
        """
        發動或取消發動指定來源技能（與爬塔相同）。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            source (str): "character、weapon 或 armor"
        """
        actor = self.fighter_by_id(self.attacker_id if self.phase == "attack" else self.defender_id)
        ability = self.cog.tower_skill_definition(actor, source)
        if ability is None or ability.get("phase") != self.phase:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle", description="此階段無法使用技能。", color=common.bot_error_color),
                ephemeral=True,
            )
            return

        # 祭血術：按鈕當下立即結算（先自傷再打對方，不進 armed、不取代普攻）
        if ability.get("id") == "blood_rite":
            if not self.cog.tower_skill_is_ready(actor, source, self.phase):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="技能尚未準備好。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            cost = int(actor.get("hp", 0)) // 3
            if int(actor.get("hp", 0)) <= 2 or cost < 1:
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="生命不足，無法發動祭血術。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            opponent = self.other_fighter(actor["user_id"])
            self.cog.tower_consume_skill(actor, source)
            self_damage = self.apply_incoming_damage(actor, cost)
            self.append_log(
                f"{actor['display_name']} 發動祭血術，自損 **{self_damage}** HP（消耗 {cost}）"
            )
            dealt = self.apply_incoming_damage(opponent, cost * 2)
            self.append_log(
                f"祭血術對 {opponent['display_name']} 造成 **{dealt}** 點傷害（跳過防守）"
            )
            # 施術者先扣血：若已倒下則施術者輸（含雙死）
            if actor["hp"] <= 0:
                await self.finish_battle(
                    winner=opponent,
                    reason="祭血術反噬，施術者倒下。",
                    interaction=interaction,
                )
                return
            if opponent["hp"] <= 0:
                await self.finish_battle(
                    winner=actor,
                    reason="對手生命歸零。",
                    interaction=interaction,
                )
                return
            await self.replace_with_fresh_view(interaction)
            return

        if self.cog.tower_is_skill_armed(actor, source):
            self.cog.tower_toggle_skill_armed(actor, source)
        else:
            if not self.cog.tower_skill_is_ready(actor, source, self.phase):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle", description="技能尚未準備好。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            self.cog.tower_toggle_skill_armed(actor, source)
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
        執行攻擊擲骰並進入防守階段（支援武器／防具技能，與爬塔對齊）。

        Args:
            interaction (discord.Interaction | None): "按鈕互動或 None"
        """
        attacker = self.fighter_by_id(self.attacker_id)
        defender = self.fighter_by_id(self.defender_id)
        skill_note = ""

        # 首次攻擊才消耗已發動技能並處理星爆／黏液等
        is_followup = self.resolving_followup
        if not is_followup:
            abilities = self.cog.tower_consume_armed_skills(attacker)
            ability_ids = {ability.get("id") for ability in abilities}
            self.pending_bind = False
            self.pending_poison = False
            self.pending_condemn = None
            self.pending_extra_attacks = []
            if abilities:
                names = "、".join(ability["name"] for ability in abilities)
                skill_note = f"（發動 {names}）"
            if "bind" in ability_ids:
                self.pending_bind = True
            if "poison" in ability_ids:
                self.pending_poison = True
            if "condemn" in ability_ids:
                self.pending_condemn = int(attacker.get("blood_feast_stacks", 0))
                attacker["blood_feast_stacks"] = 0
            if "slime" in ability_ids:
                defender["dodge_offset"] = int(defender.get("dodge_offset", 0)) - 1
                skill_note = f"{skill_note}（黏液閃避偏移 {defender['dodge_offset']:+d}）" if skill_note else f"（黏液閃避偏移 {defender['dodge_offset']:+d}）"
            if "holy_light" in ability_ids:
                before_hp = int(attacker.get("hp", 0))
                self.cog.tower_add_hp(attacker, 3)
                gained = int(attacker.get("hp", 0)) - before_hp
                skill_note = f"{skill_note}（聖光 +{gained} HP）" if skill_note else f"（聖光 +{gained} HP）"
            # 星爆／絕地反擊段數與爬塔共用 multi_attack_plan；第一段當場打，其餘排隊
            attack_plan = self.cog.multi_attack_plan(attacker, ability_ids)
            self.pending_extra_attacks = list(attack_plan[1:])
        self.resolving_followup = False

        # 攻擊擲骰與爬塔共用 roll_attack（星爆第二段起為閃避骰）
        use_dodge_roll = self.attack_uses_dodge_roll
        self.attack_uses_dodge_roll = False
        _dice, total, attack_label = self.cog.roll_attack(attacker, use_dodge_roll=use_dodge_roll)
        # 毒性蔓延：最終攻擊值加上中毒剩餘回合，並延長 1 回合
        weapon_ability = attacker.get("weapon_ability") if isinstance(attacker.get("weapon_ability"), dict) else {}
        if weapon_ability.get("id") == "toxic_spread" and int(defender.get("poison_remaining", 0)) > 0:
            poison_bonus = int(defender["poison_remaining"])
            total += poison_bonus
            defender["poison_remaining"] = poison_bonus + 1
            spread_note = f"（毒性蔓延 +{poison_bonus}）"
            skill_note = f"{skill_note}{spread_note}" if skill_note else spread_note
        if attacker.get("stance_swap_attack") and not use_dodge_roll:
            attacker["stance_swap_attack"] = False
            skill_note = f"{skill_note}（架式對調攻擊）" if skill_note else "（架式對調攻擊）"
        self.pending_attack_dice = _dice
        self.pending_attack_total = total
        attack_line = f"{attacker['display_name']} {attack_label} **{total}**{skill_note}"
        # 連擊後續段 append；新的一回合攻擊則覆寫本段紀錄開頭
        if interaction is None and self.log_text:
            self.append_log(attack_line)
        else:
            self.log_text = attack_line
        self.phase = "defend"
        # 連擊後續段不重跑防守 CD（與爬塔同回合多段攻擊一致）
        if not is_followup:
            self.prepare_defend_phase()
        else:
            self.cog.tower_clear_skill_armed(defender)

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
        for source in ("character", "armor", "weapon"):
            if not self.cog.tower_skill_is_ready(defender, source, "defend"):
                continue
            ability = self.cog.tower_skill_definition(defender, source) or {}
            if ability.get("id") == "fridge":
                if attack_total >= defender["hp"]:
                    self.cog.tower_toggle_skill_armed(defender, source)
            elif ability.get("id") == "life_conversion":
                continue
            else:
                self.cog.tower_toggle_skill_armed(defender, source)

        armed_ids = {
            (self.cog.tower_skill_definition(defender, source) or {}).get("id")
            for source in self.cog.tower_armed_sources(defender)
        }
        stance_swap_defend = "stance_swap" in armed_ids
        fridge_armed = "fridge" in armed_ids
        life_conversion_armed = "life_conversion" in armed_ids

        # 被束縛／生命轉換只能防禦；發動冰箱則選閃避
        if self.pending_bind or life_conversion_armed:
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

            agility_base = defender["agi"] + defender["agi_offset"] + int(defender.get("dodge_offset", 0))
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
        結算防禦或閃避傷害，並處理連擊／攻守互換／結束／bot 連段。

        Args:
            interaction (discord.Interaction | None): "按鈕互動或 None"
            mode (str): "defend"
            respond (bool): "True"
        """
        attacker = self.fighter_by_id(self.attacker_id)
        defender = self.fighter_by_id(self.defender_id)
        attack_total = self.pending_attack_total or 0
        abilities = self.cog.tower_consume_armed_skills(defender)
        ability_ids = {ability.get("id") for ability in abilities}
        stance_swap_defend = "stance_swap" in ability_ids
        fridge_armed = "fridge" in ability_ids
        if abilities:
            names = "、".join(ability["name"] for ability in abilities)
            skill_note = f"（發動 {names}）"
        else:
            skill_note = ""

        # 計算傷害（攻擊行已由 execute_attack 寫入；此處只 append 防守結果，避免星爆連擊被覆寫成單筆）
        defense_total = 0
        if mode == "defend":
            def_base, def_offset = self.cog.defense_roll_stats(defender, stance_swap_defend=stance_swap_defend)
            _dice, defense_total = self.cog.roll_stat(def_base, def_offset)
            if "life_conversion" in ability_ids:
                damage = attack_total
            else:
                damage = max(1, attack_total - defense_total)
            outcome_line = f"{defender['display_name']} 防禦 **{defense_total}**{skill_note}"
            if "shield_counter" in ability_ids and defense_total == attack_total:
                attacker["stun_remaining"] = 1
                outcome_line += "，盾反成功"
        else:
            dodge_offset = int(defender.get("agi_offset", 0)) + int(defender.get("dodge_offset", 0))
            _dice, dodge_total = self.cog.roll_stat(defender["agi"], dodge_offset)
            if attack_total >= dodge_total:
                damage = attack_total
                outcome_line = f"{defender['display_name']} 閃避 **{dodge_total}**{skill_note}，失敗"
            else:
                damage = 0
                outcome_line = f"{defender['display_name']} 閃避 **{dodge_total}**{skill_note}，成功，無傷！"

        # 冰箱：致死傷害改為回復
        actual_damage = 0
        if fridge_armed and damage > 0 and defender["hp"] - damage <= 0:
            heal = damage
            defender["hp"] = min(defender["max_hp"], defender["hp"] + heal)
            self.append_log(
                f"{outcome_line}\n"
                f"{defender['display_name']} 冰箱發動！傷害無效，回復 **{heal}** 點生命"
            )
            damage = 0
        else:
            if "ghost" in ability_ids:
                defender["ghost_armed"] = True
            actual_damage = self.apply_incoming_damage(defender, damage)
            if "ghost" in ability_ids and damage > 0 and actual_damage == 0:
                self.append_log(f"{outcome_line}\n幽靈化發動，傷害無效")
            elif mode == "defend" or actual_damage > 0 or damage > 0:
                self.append_log(f"{outcome_line}，受到 **{actual_damage}** 點傷害")
            else:
                self.append_log(outcome_line)

        # 最後一舞：HP≤5 時依本次實際傷害吸血
        attacker_armor = attacker.get("armor_ability") if isinstance(attacker.get("armor_ability"), dict) else {}
        if (
            attacker_armor.get("id") == "last_dance"
            and int(attacker.get("hp", 0)) <= self.cog.last_dance_hp_threshold
            and actual_damage > 0
            and int(attacker.get("hp", 0)) > 0
        ):
            before_hp = int(attacker.get("hp", 0))
            self.cog.tower_add_hp(attacker, actual_damage)
            gained = int(attacker.get("hp", 0)) - before_hp
            if gained > 0:
                self.append_log(f"最後一舞吸血 **{gained}** HP")

        # 斷罪：攻擊結算後追加傷害（不可防禦／閃避；與普攻是否命中無關）
        if self.pending_condemn is not None:
            condemn_damage = int(self.pending_condemn) * self.cog.blood_feast_damage_per_stack
            self.pending_condemn = None
            condemn_actual = self.apply_incoming_damage(defender, condemn_damage)
            self.append_log(f"斷罪造成 **{condemn_actual}** 點傷害（無視防禦／閃避）")

        if "life_conversion" in ability_ids and defender["hp"] > 0:
            self.cog.tower_add_hp(defender, defense_total)
            self.append_log(f"生命轉換回復 **{defense_total} HP**")
        if "thorn" in ability_ids and actual_damage > 0 and defender["hp"] > 0:
            reflect = actual_damage // 2
            reflected = self.apply_incoming_damage(attacker, reflect)
            self.append_log(f"反傷造成 **{reflected}** 點傷害")

        # 調整架式：接著自己的攻擊也對調
        if stance_swap_defend:
            defender["stance_swap_attack"] = True

        # 中毒：攻擊成功（實際傷害 > 0）上毒；未上成則留給連擊
        if self.pending_poison and actual_damage > 0:
            self.cog.apply_poison(defender)
            self.append_log(
                f"{defender['display_name']} 中毒"
                f"（每跳 {defender['poison_damage']}，剩餘 {defender['poison_remaining']} 回合）"
            )
            self.pending_poison = False

        # 黏液：連擊期間維持，整段攻擊結束後清除
        if not self.pending_extra_attacks:
            defender["dodge_offset"] = 0
        self.pending_attack_total = None
        self.pending_attack_dice = None
        self.pending_bind = False

        # 檢查勝負（含反傷打死攻擊方）
        if attacker["hp"] <= 0 and defender["hp"] <= 0:
            await self.finish_battle(winner=None, reason="雙方同時倒下。", interaction=interaction if respond else None)
            return
        if defender["hp"] <= 0:
            await self.finish_battle(winner=attacker, reason="對手生命歸零。", interaction=interaction if respond else None)
            return
        if attacker["hp"] <= 0:
            await self.finish_battle(winner=defender, reason="對手生命歸零。", interaction=interaction if respond else None)
            return

        # 星爆／絕地反擊：同回合追加攻擊，不換邊
        if self.pending_extra_attacks:
            extra = self.pending_extra_attacks.pop(0)
            self.attack_uses_dodge_roll = bool(extra.get("use_dodge_roll"))
            self.resolving_followup = True
            self.phase = "attack"
            if respond and interaction is not None and not interaction.response.is_done():
                new_view = await self.replace_with_fresh_view(interaction)
                await new_view.execute_attack(None)
            else:
                new_view = await self.replace_with_fresh_view(None)
                await new_view.execute_attack(None)
            return

        # 攻守互換並準備下一攻擊階段
        self.attacker_id, self.defender_id = self.defender_id, self.attacker_id
        self.phase = "attack"
        if self.prepare_attack_phase():
            dead = self.fighter_by_id(self.attacker_id)
            winner = self.other_fighter(dead["user_id"])
            await self.finish_battle(winner=winner, reason="中毒致死。", interaction=interaction if respond else None)
            return

        # 暈眩跳過攻擊
        next_attacker = self.fighter_by_id(self.attacker_id)
        if int(next_attacker.get("stun_remaining", 0)) > 0:
            next_attacker["stun_remaining"] = max(0, int(next_attacker["stun_remaining"]) - 1)
            self.append_log(f"{next_attacker['display_name']} 暈眩，跳過本次攻擊。")
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

        # 祭血術：可用就立即結算（不進 armed）
        character_ability = self.cog.tower_skill_definition(attacker, "character")
        if (
            character_ability
            and character_ability.get("id") == "blood_rite"
            and self.cog.tower_skill_is_ready(attacker, "character", "attack")
        ):
            cost = int(attacker.get("hp", 0)) // 3
            if int(attacker.get("hp", 0)) > 2 and cost >= 1:
                opponent = self.other_fighter(attacker["user_id"])
                self.cog.tower_consume_skill(attacker, "character")
                self_damage = self.apply_incoming_damage(attacker, cost)
                self.append_log(
                    f"{attacker['display_name']} 發動祭血術，自損 **{self_damage}** HP（消耗 {cost}）"
                )
                dealt = self.apply_incoming_damage(opponent, cost * 2)
                self.append_log(
                    f"祭血術對 {opponent['display_name']} 造成 **{dealt}** 點傷害（跳過防守）"
                )
                if attacker["hp"] <= 0:
                    await self.finish_battle(
                        winner=opponent,
                        reason="祭血術反噬，施術者倒下。",
                        interaction=interaction,
                    )
                    return
                if opponent["hp"] <= 0:
                    await self.finish_battle(
                        winner=attacker,
                        reason="對手生命歸零。",
                        interaction=interaction,
                    )
                    return

        # 自動發動攻擊階段可用技能（角色／武器；祭血術已立即結算，不進 armed）
        for source in ("character", "weapon"):
            if not self.cog.tower_skill_is_ready(attacker, source, "attack"):
                continue
            ability = self.cog.tower_skill_definition(attacker, source) or {}
            if ability.get("id") == "blood_rite":
                continue
            self.cog.tower_toggle_skill_armed(attacker, source)
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
        try:
            await self.finish_battle(
                winner=winner,
                reason=f"**{loser['display_name']}** 放置過久，判負。",
                interaction=None,
            )
        except Exception:
            pass


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
                member_juice = member_data["juice_battle"]
                if isinstance(member_juice.get("tower_session"), dict):
                    await interaction.response.send_message(
                        embed=Embed(
                            title="Juice Battle｜爬塔",
                            description=f"<@{member_id}> 目前已有進行中的爬塔介面。",
                            color=common.bot_error_color,
                        ),
                        ephemeral=True,
                    )
                    return
                existing_progress = member_juice.get("tower_progress")
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
            # 新開局／續爬補齊開局角色裝備快照
            user_data_map = {str(member_id): await self.cog.load_user(str(member_id)) for member_id in member_ids}
            self.cog.tower_ensure_member_loadouts(progress, user_data_map)
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
        """建立挑戰按鈕（初始鎖定防誤觸）。"""
        super().__init__(label="挑戰", style=discord.ButtonStyle.danger, disabled=True)

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
        """建立逃跑按鈕（初始鎖定防誤觸）。"""
        super().__init__(label="逃跑", style=discord.ButtonStyle.secondary, disabled=True)

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
        self.settled = False
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
        if str(interaction.user.id) not in member_ids:
            await interaction.response.send_message(
                embed=Embed(title="Juice Battle｜爬塔", description="只有本層爬塔隊員可以操作。", color=common.bot_error_color),
                ephemeral=True,
            )
            return False
        return True

    async def on_challenge(self, interaction: discord.Interaction):
        """
        將樓層入口切換成爬塔戰鬥。

        Args:
            interaction (discord.Interaction): "挑戰按鈕互動"
        """
        async with self.cog.tower_lock:
            if self.settled:
                return
            self.settled = True
            self.stop()
        await self.cog.tower_start_battle(interaction, self.progress)

    async def on_escape(self, interaction: discord.Interaction):
        """
        結束爬塔並處理暫存獎勵。

        Args:
            interaction (discord.Interaction): "逃跑按鈕互動"
        """
        async with self.cog.tower_lock:
            if self.settled:
                return
            self.settled = True
            self.stop()
        await self.cog.tower_escape(interaction, self.progress)

    async def on_timeout(self) -> None:
        """
        樓層介面逾時後解除爬塔介面鎖定，但保留進度供下次續爬。
        """
        member_ids = [str(member_id) for member_id in self.progress.get("member_ids") or []]
        async with self.cog.tower_lock:
            if self.settled:
                return
            existing = await self.cog.tower_load_shared_progress(member_ids)
            if existing is None:
                return
            self.settled = True
            self.stop()
            for member_id in member_ids:
                await self.cog.clear_tower_session(member_id)
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
        if str(interaction.user.id) not in member_ids:
            await interaction.response.send_message(
                embed=Embed(
                    title="Juice Battle｜爬塔",
                    description="只有本次爬塔隊員可以進入下一層。",
                    color=common.bot_error_color,
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_next_floor(self, interaction: discord.Interaction):
        """
        顯示下一層怪物與挑戰／逃跑按鈕。

        Args:
            interaction (discord.Interaction): "前往下一層按鈕互動"
        """
        async with self.cog.tower_lock:
            if self.finished:
                return
            self.finished = True
            self.stop()
        next_view = JuiceBattleTowerFloorView(cog=self.cog, progress=self.progress)
        next_view.message = self.message
        await interaction.response.edit_message(
            embed=self.cog.tower_floor_embed(self.progress),
            view=next_view,
        )
        self.cog.schedule_tower_button_unlock(next_view)

    async def on_timeout(self) -> None:
        """
        通關結果介面逾時後保存進度並解除爬塔介面鎖定。
        """
        member_ids = [str(member_id) for member_id in self.progress.get("member_ids") or []]
        async with self.cog.tower_lock:
            if self.finished:
                return
            existing = await self.cog.tower_load_shared_progress(member_ids)
            if existing is None:
                return
            self.finished = True
            self.stop()
            for member_id in member_ids:
                await self.cog.clear_tower_session(member_id)
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

    def __init__(self, *, source: str, label: str, armed: bool, disabled: bool = False):
        """
        建立技能按鈕。

        Args:
            source (str): "技能來源"
            label (str): "按鈕顯示文字"
            armed (bool): "是否已發動"
            disabled (bool): "是否鎖定（例如 CD 中）"
        """
        display = f"{label}（已發動）" if armed else label
        super().__init__(label=display, style=discord.ButtonStyle.success, disabled=disabled)
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
        self.timed_out = False
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
            poison_damage = int(self.monster.get("poison_damage", self.cog.poison_base_damage))
            monster_status.append(f"中毒({poison_damage}) {self.monster['poison_remaining']}")
        # 黏液：面板顯示閃避偏移；攻擊階段發動中則預覽 -1
        monster_dodge_offset = int(self.monster.get("dodge_offset", 0))
        slime_preview = False
        if self.phase == "player_attack":
            actor = self.current_actor()
            if actor is not None:
                slime_preview = any(
                    (self.cog.tower_skill_definition(actor, source) or {}).get("id") == "slime"
                    for source in self.cog.tower_armed_sources(actor)
                )
        if slime_preview:
            monster_dodge_offset -= 1
        if monster_dodge_offset != 0:
            monster_status.append(f"黏液閃避偏移 {monster_dodge_offset:+d}")
        monster_text = (
            f"生命 **{self.monster['hp']}/{self.monster['max_hp']}**\n"
            f"攻擊 {self.monster['atk']}({self.monster.get('attack_offset', 0):+d})｜"
            f"防禦 {self.monster['defense']}｜"
            f"敏捷 {self.monster['agi']}({monster_dodge_offset:+d})"
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
                armor_ability = fighter.get("armor_ability") if isinstance(fighter.get("armor_ability"), dict) else {}
                if armor_ability.get("id") == "toxic_revival":
                    status.append(f"毒性回生 {fighter['poison_remaining']}")
                else:
                    poison_damage = int(fighter.get("poison_damage", self.cog.poison_base_damage))
                    status.append(f"中毒({poison_damage}) {fighter['poison_remaining']}")
            if int(fighter.get("blood_feast_stacks", 0)) > 0:
                status.append(f"血宴 {fighter['blood_feast_stacks']}")
            if fighter.get("berserk_triggered"):
                status.append("暴走")
            if int(fighter.get("dodge_offset", 0)) != 0:
                status.append(f"黏液閃避偏移 {fighter['dodge_offset']:+d}")
            armed_abilities = [
                ability
                for source in self.cog.tower_armed_sources(fighter)
                for ability in [self.cog.tower_skill_definition(fighter, source)]
                if ability is not None
            ]
            stance_active = bool(fighter.get("stance_swap_attack")) or any(
                ability.get("id") == "stance_swap" for ability in armed_abilities
            )
            if armed_abilities:
                names = "、".join(ability["name"] for ability in armed_abilities)
                status.append(f"已發動：{names}")
            elif stance_active:
                status.append("架式對調中")
            status_text = f"\n狀態：{'／'.join(status)}" if status else ""
            # 架式只對調角色數值，偏移維持攻擊／防禦欄位
            if stance_active:
                display_atk = fighter["defense"]
                display_def = fighter["atk"]
            else:
                display_atk = fighter["atk"]
                display_def = fighter["defense"]
            display_atk_offset = int(fighter.get("atk_offset", 0)) + int(fighter.get("berserk_offset", 0))
            display_def_offset = int(fighter.get("def_offset", 0))
            embed.add_field(
                name=f"{fighter['display_name']}（{fighter['character_name']}）",
                value=(
                    f"HP **{fighter['hp']}/{fighter['max_hp']}**\n"
                    f"攻擊 {display_atk}({display_atk_offset:+d})｜"
                    f"防禦 {display_def}({display_def_offset:+d})｜"
                    f"敏捷 {fighter['agi']}({fighter.get('agi_offset', 0) + fighter.get('dodge_offset', 0):+d})"
                    f"{status_text}"
                ),
                inline=False,
            )
        if self.log_text:
            embed.add_field(name="戰鬥紀錄", value=self.log_text[:1024], inline=False)
        if self.timed_out:
            action_text = "操作逾時"
        elif self.finished:
            action_text = "本層已通關"
        else:
            action_text = "戰鬥處理中"
        if not self.finished and self.phase == "player_attack" and self.current_actor() is not None:
            actor = self.current_actor()
            action_text = f"輪到 **{actor['display_name']}** 攻擊"
            armed_abilities = [
                ability
                for source in self.cog.tower_armed_sources(actor)
                for ability in [self.cog.tower_skill_definition(actor, source)]
                if ability is not None
            ]
            if armed_abilities:
                names = "、".join(ability["name"] for ability in armed_abilities)
                action_text += f"\n已發動：**{names}**"
        elif not self.finished and self.phase == "player_defend" and self.pending_target_id:
            defender = self.fighter_by_id(self.pending_target_id)
            action_text = f"輪到 **{defender['display_name']}** 選擇防禦或閃避"
            if self.pending_bind:
                action_text = f"輪到 **{defender['display_name']}** 選擇防禦（被束縛，無法閃避）"
            armed_abilities = [
                ability
                for source in self.cog.tower_armed_sources(defender)
                for ability in [self.cog.tower_skill_definition(defender, source)]
                if ability is not None
            ]
            if armed_abilities:
                names = "、".join(ability["name"] for ability in armed_abilities)
                action_text += f"\n已發動：**{names}**"
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
                button = self.build_skill_button(actor, source, "attack")
                if button is not None:
                    self.add_item(button)
        elif self.phase == "player_defend":
            defender = self.fighter_by_id(self.pending_target_id or "")
            if defender is None:
                return
            self.add_item(JuiceBattleTowerDefendButton())
            life_conversion_armed = any(
                (self.cog.tower_skill_definition(defender, source) or {}).get("id") == "life_conversion"
                for source in self.cog.tower_armed_sources(defender)
            )
            if not self.pending_bind and not life_conversion_armed:
                self.add_item(JuiceBattleTowerDodgeButton())
            for source in ("character", "armor", "weapon"):
                button = self.build_skill_button(defender, source, "defend")
                if button is not None:
                    self.add_item(button)

    def build_skill_button(self, fighter: dict, source: str, phase: str):
        """
        建立爬塔技能按鈕；CD／已使用時改為停用顯示，避免按鈕消失。

        Args:
            fighter (dict): "目前行動的玩家"
            source (str): "character、weapon 或 armor"
            phase (str): "attack 或 defend"

        Returns:
            button (JuiceBattleTowerSkillButton | None): "可顯示的技能按鈕"
        """
        ability = self.cog.tower_skill_definition(fighter, source)
        if ability is None or ability.get("phase") != phase:
            return None
        base_label = f"{self.cog.skill_source_label(source)}：{ability['name']}"
        armed = self.cog.tower_is_skill_armed(fighter, source)
        # 祭血術：HP≤2 或消耗 <1 時按鈕停用（不進 CD）
        blood_rite_blocked = False
        if ability.get("id") == "blood_rite":
            cost = int(fighter.get("hp", 0)) // 3
            blood_rite_blocked = int(fighter.get("hp", 0)) <= 2 or cost < 1
        if armed or self.cog.tower_skill_is_ready(fighter, source, phase):
            return JuiceBattleTowerSkillButton(
                source=source,
                label=base_label,
                armed=armed,
                disabled=blood_rite_blocked and not armed,
            )
        if ability.get("cd") is None:
            if not fighter.get(f"{source}_skill_used"):
                return None
            return JuiceBattleTowerSkillButton(
                source=source,
                label=f"{base_label}（已使用）",
                armed=False,
                disabled=True,
            )
        cd_left = int(fighter.get(f"{source}_skill_cd", 0))
        if cd_left <= 0:
            return None
        return JuiceBattleTowerSkillButton(
            source=source,
            label=f"{base_label}（CD {cd_left}）",
            armed=False,
            disabled=True,
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
        self.cog.tower_clear_skill_armed(fighter)
        fighter["dodge_offset"] = 0
        # 中毒跳傷；翠毒披肩改為毒性回生
        if int(fighter.get("poison_remaining", 0)) > 0:
            armor_ability = fighter.get("armor_ability") if isinstance(fighter.get("armor_ability"), dict) else {}
            if armor_ability.get("id") == "toxic_revival":
                before_hp = int(fighter.get("hp", 0))
                self.cog.tower_add_hp(fighter, self.cog.toxic_revival_heal)
                gained = int(fighter.get("hp", 0)) - before_hp
                fighter["poison_remaining"] = max(0, int(fighter["poison_remaining"]) - 1)
                if fighter["poison_remaining"] <= 0:
                    fighter["poison_damage"] = 0
                self.append_log(
                    f"{fighter['display_name']} 毒性回生，回復 **{gained}** HP（剩餘 {fighter['poison_remaining']} 回合）"
                )
            else:
                tick_damage = int(fighter.get("poison_damage", self.cog.poison_base_damage))
                damage = self.apply_damage(fighter, tick_damage)
                fighter["poison_remaining"] = max(0, int(fighter["poison_remaining"]) - 1)
                if fighter["poison_remaining"] <= 0:
                    fighter["poison_damage"] = 0
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
        if actual_damage > 0:
            weapon_ability = target.get("weapon_ability") if isinstance(target.get("weapon_ability"), dict) else {}
            if weapon_ability.get("id") == "condemn":
                target["blood_feast_stacks"] = int(target.get("blood_feast_stacks", 0)) + 1
            if count_damage:
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
        # 大跑就緒且閃避 > 0 時強制閃避（閃避為 0 不發動）
        if (
            self.monster_skill_ready("defend")
            and ability.get("id") == "sprint"
            and int(self.monster.get("agi", 0)) != 0
        ):
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
        # 攻擊擲骰與挑戰戰共用 roll_attack（星爆第二段為閃避骰）
        _dice, attack_total, attack_label = self.cog.roll_attack(attacker, use_dodge_roll=use_dodge_roll)
        if attacker.get("stance_swap_attack"):
            attacker["stance_swap_attack"] = False
        # 毒性蔓延：最終攻擊值加上中毒剩餘回合，並延長 1 回合
        weapon_ability = attacker.get("weapon_ability") if isinstance(attacker.get("weapon_ability"), dict) else {}
        spread_note = ""
        if weapon_ability.get("id") == "toxic_spread" and int(self.monster.get("poison_remaining", 0)) > 0:
            poison_bonus = int(self.monster["poison_remaining"])
            attack_total += poison_bonus
            self.monster["poison_remaining"] = poison_bonus + 1
            spread_note = f"（毒性蔓延 +{poison_bonus}）"
        mode = self.choose_monster_defense(attack_total, bound)
        if mode == "stunned":
            damage = self.apply_damage(self.monster, attack_total)
            self.last_attack_damage = damage
            self.monster["stun_remaining"] = max(0, int(self.monster.get("stun_remaining", 0)) - 1)
            result = (
                f"{attacker['display_name']} {attack_label} **{attack_total}**{spread_note}，"
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
                f"{attacker['display_name']} {attack_label} **{attack_total}**{spread_note}，"
                f"怪物防禦 **{defense_total}**，受到 **{actual_damage}** 傷害{hardening_text}"
            )
        else:
            # 大跑：閃避數值變兩倍，不加倍偏移
            dodge_base = int(self.monster.get("agi", 0))
            if self.monster.get("sprint_armed"):
                dodge_base *= 2
            dodge_offset = int(self.monster.get("dodge_offset", 0))
            _dodge_dice, dodge_total, dodge_text = self.cog.tower_roll(
                self.monster,
                dodge_base,
                dodge_offset,
            )
            if attack_total >= dodge_total:
                damage = self.apply_damage(self.monster, attack_total)
                self.last_attack_damage = damage
                result = (
                    f"{attacker['display_name']} {attack_label} **{attack_total}**{spread_note}，"
                    f"怪物閃避 **{dodge_total}**，失敗，受到 **{damage}** 傷害"
                )
            else:
                self.last_attack_damage = 0
                result = (
                    f"{attacker['display_name']} {attack_label} **{attack_total}**{spread_note}，"
                    f"怪物閃避 **{dodge_total}**，成功，無傷"
                )
            self.monster["sprint_armed"] = False
        # 最後一舞：HP≤5 時依本次實際傷害吸血
        armor_ability = attacker.get("armor_ability") if isinstance(attacker.get("armor_ability"), dict) else {}
        if (
            armor_ability.get("id") == "last_dance"
            and int(attacker.get("hp", 0)) <= self.cog.last_dance_hp_threshold
            and self.last_attack_damage > 0
            and int(attacker.get("hp", 0)) > 0
        ):
            before_hp = int(attacker.get("hp", 0))
            self.cog.tower_add_hp(attacker, self.last_attack_damage)
            gained = int(attacker.get("hp", 0)) - before_hp
            if gained > 0:
                result = f"{result}\n最後一舞吸血 **{gained}** HP"
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

        # 祭血術：按鈕當下立即結算（先自傷再打怪物，不進 armed、不取代普攻）
        if ability.get("id") == "blood_rite":
            if not self.cog.tower_skill_is_ready(actor, source, phase):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle｜爬塔", description="技能尚未準備好。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            cost = int(actor.get("hp", 0)) // 3
            if int(actor.get("hp", 0)) <= 2 or cost < 1:
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle｜爬塔", description="生命不足，無法發動祭血術。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            self.cog.tower_consume_skill(actor, source)
            self_damage = self.apply_damage(actor, cost)
            self.append_log(
                f"{actor['display_name']} 發動祭血術，自損 **{self_damage}** HP（消耗 {cost}）"
            )
            dealt = self.apply_damage(self.monster, cost * 2)
            self.append_log(
                f"祭血術對 {self.monster['name']} 造成 **{dealt}** 點傷害（跳過防守）"
            )
            # 施術者先扣血：全滅則判敗（含雙死）；否則怪物死則通關
            if not self.living_fighters():
                await self.cog.tower_finish_defeat(self, "祭血術反噬，全員倒下。")
                return
            if self.monster["hp"] <= 0:
                await self.cog.tower_finish_floor(self, self.log_text)
                return
            # 施術者倒下但隊友仍在：結束其攻擊回合
            if actor["hp"] <= 0:
                self.append_log(f"{actor['display_name']} 倒下。")
                await self.enter_next_player()
                return
            self.rebuild_buttons()
            await self.save_battle_state()
            if self.message is not None:
                await self.message.edit(embed=self.build_embed(), view=self)
            return

        if self.cog.tower_is_skill_armed(actor, source):
            self.cog.tower_toggle_skill_armed(actor, source)
        else:
            if not self.cog.tower_skill_is_ready(actor, source, phase):
                await interaction.response.send_message(
                    embed=Embed(title="Juice Battle｜爬塔", description="技能尚未準備好。", color=common.bot_error_color),
                    ephemeral=True,
                )
                return
            self.cog.tower_toggle_skill_armed(actor, source)
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
        abilities = self.cog.tower_consume_armed_skills(attacker)
        ability_ids = {ability.get("id") for ability in abilities}
        attacker["pending_poison"] = False
        bind = False
        results = []
        if "bind" in ability_ids:
            bind = True
        if "poison" in ability_ids:
            attacker["pending_poison"] = True
        # 斷罪：消耗血宴，於首次攻擊後追加傷害
        condemn_damage = None
        if "condemn" in ability_ids:
            condemn_damage = int(attacker.get("blood_feast_stacks", 0)) * self.cog.blood_feast_damage_per_stack
            attacker["blood_feast_stacks"] = 0
        if "slime" in ability_ids:
            self.monster["dodge_offset"] = int(self.monster.get("dodge_offset", 0)) - 1
            results.append(f"{self.monster['name']} 被黏液影響，閃避偏移 {self.monster['dodge_offset']:+d}")
        if "holy_light" in ability_ids:
            # 只補存活隊員，不能救活已倒下的人
            heal_parts = []
            for fighter in self.living_fighters():
                before_hp = int(fighter.get("hp", 0))
                self.cog.tower_add_hp(fighter, 3)
                gained = int(fighter.get("hp", 0)) - before_hp
                heal_parts.append(f"{fighter['display_name']} +{gained}")
            results.append(f"聖光發動，存活隊員回復：**{'／'.join(heal_parts)}**")
        # 星爆／絕地反擊段數與挑戰戰共用 multi_attack_plan
        attack_plan = self.cog.multi_attack_plan(attacker, ability_ids)
        for attack_index, plan_entry in enumerate(attack_plan):
            result = self.resolve_player_attack(
                attacker,
                use_dodge_roll=bool(plan_entry.get("use_dodge_roll")),
                bound=bind and attack_index == 0,
            )
            results.append(result)
            if condemn_damage is not None:
                condemn_actual = self.apply_damage(self.monster, condemn_damage)
                results.append(f"斷罪造成 **{condemn_actual}** 點傷害（無視防禦／閃避）")
                condemn_damage = None
            if self.monster["hp"] <= 0:
                break
            if attacker.get("pending_poison") and self.last_attack_damage > 0:
                if self.monster.get("id") != "poison_bubble_bug":
                    self.cog.apply_poison(self.monster)
                    results.append(
                        f"怪物中毒（每跳 {self.monster['poison_damage']}，"
                        f"剩餘 {self.monster['poison_remaining']} 回合）。"
                    )
                attacker["pending_poison"] = False
        attacker["pending_poison"] = False
        self.log_text = "\n".join(results)
        # 黏液只影響本次攻擊的閃避結算
        self.monster["dodge_offset"] = 0
        if self.monster["hp"] <= 0:
            await self.cog.tower_finish_floor(self, self.log_text)
            return
        # 不在此清空按鈕，交給 enter_next_player 刷新下一動作者介面
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
            tick_damage = int(self.monster.get("poison_damage", self.cog.poison_base_damage))
            poison_damage = self.apply_damage(self.monster, tick_damage)
            self.monster["poison_remaining"] = max(0, int(self.monster["poison_remaining"]) - 1)
            if self.monster["poison_remaining"] <= 0:
                self.monster["poison_damage"] = 0
            self.append_log(
                f"{self.monster['name']} 中毒，受到 **{poison_damage}** 點傷害"
                f"（剩餘 {self.monster['poison_remaining']} 回合）"
            )
            if self.monster["hp"] <= 0:
                await self.cog.tower_finish_floor(self, self.log_text)
                return
        if self.monster.get("id") == "mushroom":
            self.cog.tower_add_hp(self.monster, 1)
            self.append_log("蘑菇的增殖發動，怪物回復 **1 HP**。")
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
        self.cog.tower_clear_skill_armed(target)
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
        abilities = self.cog.tower_consume_armed_skills(defender)
        ability_ids = {ability.get("id") for ability in abilities}
        attack_total = int(self.pending_attack_total)
        damage = 0
        if abilities:
            names = "、".join(ability["name"] for ability in abilities)
            defender_skill_note = f"（發動 {names}）"
        else:
            defender_skill_note = ""
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
            stance_swap = "stance_swap" in ability_ids
            # 架式只對調角色數值，防禦偏移維持原欄位
            defense_base, defense_offset = self.cog.defense_roll_stats(
                defender,
                stance_swap_defend=stance_swap,
            )
            defense_dice, defense_total, _defense_text = self.cog.tower_roll(
                defender,
                defense_base,
                defense_offset,
            )
            if "life_conversion" in ability_ids:
                damage = attack_total
            else:
                damage = max(1, attack_total - defense_total)
            log_parts.append(f"{defender['display_name']} 防禦 **{defense_total}**{defender_skill_note}")
            if "shield_counter" in ability_ids and defense_total == attack_total:
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
        fridge_armed = "fridge" in ability_ids
        if fridge_armed and damage > 0 and int(defender["hp"]) - damage <= 0:
            heal = damage
            defender["hp"] = min(int(defender["max_hp"]), int(defender["hp"]) + heal)
            log_parts.append(f"{defender['display_name']} 冰箱發動！傷害無效，回復 **{heal}** 點生命")
            actual_damage = 0
        else:
            ghost = "ghost" in ability_ids
            if ghost:
                defender["ghost_armed"] = True
            actual_damage = self.apply_damage(defender, damage)
            if ghost:
                log_parts.append("幽靈化發動，傷害無效")
            else:
                log_parts.append(f"受到 **{actual_damage}** 點傷害")

        if "life_conversion" in ability_ids and defender["hp"] > 0:
            self.cog.tower_add_hp(defender, defense_total)
            log_parts.append(f"生命轉換回復 **{defense_total} HP**")
        # 反傷需發動荊棘盔甲技能，不是穿著就觸發
        if "thorn" in ability_ids and actual_damage > 0 and defender["hp"] > 0:
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
        # 部落弓箭手：攻擊成功時賦予中毒（對齊 apply_poison）
        if monster_ability.get("id") == "poison" and actual_damage > 0:
            self.cog.apply_poison(defender)
            log_parts.append(
                f"{defender['display_name']} 中毒"
                f"（每跳 {defender['poison_damage']}，剩餘 {defender['poison_remaining']} 回合）"
            )
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
        async with self.cog.tower_lock:
            if self.finished:
                return
            self.finished = True
            self.timed_out = True
            self.stop()
            # 已死亡／結算清掉進度後，禁止再寫回進度或覆寫結算畫面
            if not self.living_fighters():
                await self.cog.tower_clear_progress(self.member_ids)
                show_timeout_embed = False
            else:
                existing = await self.cog.tower_load_shared_progress(self.member_ids)
                if existing is None:
                    return
                await self.save_battle_state()
                for member_id in self.member_ids:
                    await self.cog.clear_tower_session(member_id)
                show_timeout_embed = True
        self.rebuild_buttons()
        if self.message is None:
            return
        try:
            if not show_timeout_embed:
                await self.message.edit(
                    embed=Embed(
                        title="Juice Battle｜爬塔失敗",
                        description="所有我方成員都已死亡。\n本次爬塔的蛋糕、裝備與進度全部消失。",
                        color=common.bot_error_color,
                    ),
                    view=None,
                )
                return
            embed = self.build_embed()
            embed.description = "戰鬥操作逾時，已保存本場戰鬥狀態；請重新使用指令繼續。"
            await self.message.edit(embed=embed, view=None)
        except Exception:
            pass


class JuiceBattleTowerClaimButton(discord.ui.Button):
    """爬塔裝備領取者按鈕。"""

    def __init__(self, *, member_id: str, label: str):
        """
        建立裝備領取者按鈕。

        Args:
            member_id (str): "領取者 ID"
            label (str): "按鈕顯示文字"
        """
        super().__init__(label=label, style=discord.ButtonStyle.primary, disabled=True)
        self.member_id = member_id

    async def callback(self, interaction: discord.Interaction):
        """
        指定目前裝備的領取者。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerRewardView = self.view  # type: ignore[assignment]
        await view.on_decide(interaction, self.member_id)


class JuiceBattleTowerDiscardButton(discord.ui.Button):
    """爬塔裝備丟棄按鈕。"""

    def __init__(self):
        """
        建立紅色丟棄按鈕。
        """
        super().__init__(label="丟棄", style=discord.ButtonStyle.danger, disabled=True)

    async def callback(self, interaction: discord.Interaction):
        """
        丟棄目前待處理裝備。

        Args:
            interaction (discord.Interaction): "按鈕互動"
        """
        view: JuiceBattleTowerRewardView = self.view  # type: ignore[assignment]
        await view.on_decide(interaction, None)


class JuiceBattleTowerRewardView(discord.ui.View):
    """單人／雙人爬塔的裝備領取介面。"""

    def __init__(self, *, cog: JuiceBattle, progress: dict, pending_index: int, recipients: list[str | None]):
        """
        建立裝備領取 View。

        Args:
            cog (JuiceBattle): "Juice Battle cog"
            progress (dict): "爬塔快照"
            pending_index (int): "目前處理的裝備索引"
            recipients (list[str | None]): "已決定的領取者；None 表示丟棄"
        """
        super().__init__(timeout=cog.tower_view_timeout)
        self.cog = cog
        self.progress = copy.deepcopy(progress)
        self.pending_index = pending_index
        self.recipients = list(recipients)
        self.message: discord.Message | None = None
        self.claimed = False
        self.bonus_report: dict | None = None
        self.rebuild_buttons()

    def equipment_name(self, item_id: str) -> str:
        """
        依裝備 ID 取得顯示名稱。

        Args:
            item_id (str): "裝備 ID"

        Returns:
            name (str): "裝備名稱"
        """
        template = self.cog.item_template("weapon", item_id) or self.cog.item_template("armor", item_id)
        return template["name"] if template else str(item_id)

    def item_name(self) -> str:
        """
        取得目前待領取裝備名稱。

        Returns:
            name (str): "裝備名稱"
        """
        pending = self.progress.get("pending_equipment") or []
        if self.pending_index < 0 or self.pending_index >= len(pending):
            return "未知裝備"
        return self.equipment_name(str(pending[self.pending_index]))

    def decision_summary(self) -> str:
        """
        組出已領取／已丟棄裝備摘要。

        Returns:
            summary (str): "多行摘要文字；尚無決定時為空字串"
        """
        pending = self.progress.get("pending_equipment") or []
        names = self.progress.get("member_names") if isinstance(self.progress.get("member_names"), dict) else {}
        lines = []
        for index, recipient_id in enumerate(self.recipients):
            if index >= len(pending):
                break
            item_name = self.equipment_name(str(pending[index]))
            if recipient_id is None:
                lines.append(f"・**{item_name}**：已丟棄")
                continue
            owner_name = str(names.get(str(recipient_id)) or recipient_id)
            lines.append(f"・**{item_name}**：已由 **{owner_name}** 領取")
        return "\n".join(lines)

    def build_embed(self) -> Embed:
        """
        建立裝備領取選擇 embed。

        Returns:
            embed (Embed): "裝備領取資訊"
        """
        total = len(self.progress.get("pending_equipment") or [])
        current = min(self.pending_index + 1, max(total, 1))
        description = (
            f"請決定第 **{current}/{total}** 件裝備：**{self.item_name()}**。\n"
            f"可指定領取者，或按「丟棄」放棄這件裝備。\n"
            f"蛋糕：**{int(self.progress.get('pending_cake', 0))}** {common.cake_emoji}"
        )
        decided = self.decision_summary()
        if decided:
            description += f"\n\n已處理：\n{decided}"
        return Embed(
            title="Juice Battle｜領取爬塔裝備",
            description=description,
            color=common.bot_color,
        )

    def build_settle_embed(self, *, timed_out: bool = False) -> Embed:
        """
        建立領取完成或逾時後的結算 embed。

        Args:
            timed_out (bool): "是否因逾時自動發放剩餘裝備"

        Returns:
            embed (Embed): "結算訊息"
        """
        summary = self.decision_summary()
        if timed_out:
            description = (
                "領取操作逾時，未決定的裝備已交給隊伍發起者；蛋糕與最高樓層紀錄已結算。"
            )
        else:
            description = (
                f"已成功逃跑並取得 **{int(self.progress.get('pending_cake', 0))}** {common.cake_emoji}。\n"
                f"最高通關：第 **{int(self.progress.get('cleared_floor', 0))}** 層。"
            )
        if summary:
            description += f"\n\n裝備結果：\n{summary}"
        embed = Embed(
            title="Juice Battle｜爬塔結算",
            description=description,
            color=common.bot_color,
        )
        self.cog.tower_add_cake_bonus_fields(embed, self.bonus_report)
        return embed

    def rebuild_buttons(self):
        """
        依隊員重建裝備領取與丟棄按鈕。
        """
        self.clear_items()
        names = self.progress.get("member_names") if isinstance(self.progress.get("member_names"), dict) else {}
        for member_id in self.progress.get("member_ids") or []:
            label = str(names.get(str(member_id)) or member_id)
            self.add_item(JuiceBattleTowerClaimButton(member_id=str(member_id), label=f"{label}領取"))
        self.add_item(JuiceBattleTowerDiscardButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        只允許爬塔隊員指定裝備領取者或丟棄。

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

    async def on_decide(self, interaction: discord.Interaction, recipient_id: str | None):
        """
        記錄一件裝備的領取或丟棄，並進入下一件或結算。

        Args:
            interaction (discord.Interaction): "按鈕互動"
            recipient_id (str | None): "領取者 ID；None 表示丟棄"
        """
        # 防止雙人同時搶按造成重複發放
        if self.claimed:
            await interaction.response.send_message(
                embed=Embed(
                    title="Juice Battle｜爬塔",
                    description="這件裝備已經處理過了（已領取或已丟棄）。",
                    color=common.bot_error_color,
                ),
                ephemeral=True,
            )
            return
        self.claimed = True
        self.recipients.append(str(recipient_id) if recipient_id is not None else None)
        total = len(self.progress.get("pending_equipment") or [])
        # 尚有下一件裝備：進入下一張領取介面
        if self.pending_index + 1 < total:
            self.stop()
            next_view = JuiceBattleTowerRewardView(
                cog=self.cog,
                progress=self.progress,
                pending_index=self.pending_index + 1,
                recipients=self.recipients,
            )
            next_view.message = self.message
            await interaction.response.edit_message(embed=next_view.build_embed(), view=next_view)
            self.cog.schedule_tower_button_unlock(next_view)
            return
        # 全部決定完畢：先 stop 再發放，避免逾時與結算競態
        self.stop()
        self.bonus_report = await self.cog.tower_grant_rewards(self.progress, self.recipients)
        await interaction.response.edit_message(embed=self.build_settle_embed(), view=None)

    async def on_timeout(self) -> None:
        """
        領取介面逾時時將未決定裝備交給隊伍第一位成員；已丟棄者不發放。
        """
        if self.claimed or self.is_finished():
            return
        self.claimed = True
        self.stop()
        member_ids = [str(member_id) for member_id in self.progress.get("member_ids") or []]
        async with self.cog.tower_lock:
            existing = await self.cog.tower_load_shared_progress(member_ids)
            if existing is None:
                return
        fallback_id = member_ids[0] if member_ids else None
        while len(self.recipients) < len(self.progress.get("pending_equipment") or []):
            self.recipients.append(fallback_id)
        self.bonus_report = await self.cog.tower_grant_rewards(self.progress, self.recipients)
        if self.message is not None:
            try:
                await self.message.edit(embed=self.build_settle_embed(timed_out=True), view=None)
            except Exception:
                pass


async def setup(client: commands.Bot):
    """
    載入 Juice Battle cog。

    Args:
        client (commands.Bot): "Natalie bot"
    """
    await client.add_cog(JuiceBattle(client))
