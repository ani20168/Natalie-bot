import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
import random
import itertools
import re
from typing import Optional, Tuple, Union
import asyncio
import time



class MiningGame(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.pickaxe_list = {
        "基本礦鎬": {"耐久度": 100, "需求等級": 1, "價格": 0},
        "石鎬": {"耐久度": 200, "需求等級": 6, "價格": 500},
        "鐵鎬": {"耐久度": 400, "需求等級": 12, "價格": 2000},
        "鑽石鎬": {"耐久度": 650, "需求等級": 18, "價格": 3000},
        "不要鎬": {"耐久度": 1000, "需求等級": 25, "價格": 5000}
        }
        self.mineral_chancelist = {
        "森林礦坑": {"石頭": 0.3, "鐵礦": 0.45, "金礦": 0.25, "鈦晶": 0, "鑽石": 0, "輝煌水晶": 0},
        "荒野高原": {"石頭": 0.1, "鐵礦": 0.45, "金礦": 0.25, "鈦晶": 0.2, "鑽石": 0, "輝煌水晶": 0},
        "蛋糕仙境": {"石頭": 0, "鐵礦": 0.38, "金礦": 0.32, "鈦晶": 0.25, "鑽石": 0.05, "輝煌水晶": 0},
        "永世凍土": {"石頭": 0, "鐵礦": 0.25, "金礦": 0.36, "鈦晶": 0.27, "鑽石": 0.12, "輝煌水晶": 0},
        "熾熱火炎山": {"石頭": 0, "鐵礦": 0, "金礦": 0.43, "鈦晶": 0.35, "鑽石": 0.22, "輝煌水晶": 0},
        "虛空洞穴": {"石頭": 0, "鐵礦": 0, "金礦": 0.3, "鈦晶": 0.4, "鑽石": 0.3, "輝煌水晶": 0},
        "天境之地": {"石頭": 0, "鐵礦": 0, "金礦": 0.15, "鈦晶": 0.25, "鑽石": 0.4, "輝煌水晶": 0.2}
        }
        self.mine_levellimit = {
            "森林礦坑": 1,
            "荒野高原": 10,
            "蛋糕仙境": 18,
            "永世凍土": 26,
            "熾熱火炎山": 34,
            "虛空洞穴": 42,
            "天境之地": 70
        }
        self.collection_list = {
        "森林礦坑": ["昆蟲化石", "遠古的妖精翅膀", "萬年神木之根", "古代陶器碎片", "腐化的鹿角", "地脈結晶碎塊"],
        "荒野高原": ["風的根源石", "儀式石碑", "被詛咒的匕首", "神祕骷髏項鍊", "乾枯的圖騰羽毛"],
        "蛋糕仙境": ["不滅的蠟燭", "蛋糕製造機", "異界之門鑰匙"],
        "永世凍土": ["雪怪排泄物", "冰鎮草莓甜酒", "冰凍章魚觸手", "凍結的極光碎片"],
        "熾熱火炎山": ["上古琥珀", "火龍遺骨", "地獄辣炒年糕"],
        "虛空洞穴": ["反物質研究手稿", "異星生物黏液", "深淵的彼岸花"],
        "天境之地": ["沉沒的三叉戟", "碎裂的傳送石", "雲海凝結之露"]
        }
        self.mineral_pricelist = {
            "鐵礦": 5,
            "金礦": 10,
            "鈦晶": 20,
            "鑽石": 50,
            "輝煌水晶": 120
        }
        self.pickaxe_bag_size = 7
        self.skill_pickaxe_shop = {
            "災禍鎬": {"需求等級": 50, "價格": 10000},
            "附魔迷你船錨": {"需求等級": 64, "價格": 20000},
        }


    def miningdata_read(self,userid: str):
        data = common.dataload("data/mining.json")

        if userid not in data:
            data[userid] = {
                "pickaxe": "基本礦鎬",
                "mine": "森林礦坑",
                "pickaxe_health": 100,
                "pickaxe_maxhealth": 100,
                "autofix": False,
                "collections": {}
                }
            common.datawrite(data,"data/mining.json")

        #新增自動挖礦機的資料
        if "machine_amount" not in data[userid]:
            data[userid]["machine_amount"] = 0
            data[userid]["machine_mine"] = "森林礦坑"
            common.datawrite(data,"data/mining.json")

        # 技能礦鎬裝備背包（7 格）與卸下還原用快照
        bag_migrated = False
        if "pickaxe_bag" not in data[userid]:
            data[userid]["pickaxe_bag"] = [None] * self.pickaxe_bag_size
            bag_migrated = True
        elif len(data[userid]["pickaxe_bag"]) != self.pickaxe_bag_size:
            new_bag = [None] * self.pickaxe_bag_size
            for index in range(min(len(data[userid]["pickaxe_bag"]), self.pickaxe_bag_size)):
                new_bag[index] = data[userid]["pickaxe_bag"][index]
            data[userid]["pickaxe_bag"] = new_bag
            bag_migrated = True
        if "equipped_bag_slot" not in data[userid]:
            data[userid]["equipped_bag_slot"] = None
            bag_migrated = True
        if "legacy_pickaxe_state" not in data[userid]:
            data[userid]["legacy_pickaxe_state"] = None
            bag_migrated = True
        if bag_migrated:
            common.datawrite(data,"data/mining.json")

        # 新礦場上線時補齊每日挖掘量條目
        if "mine_mininglimit" not in data:
            data["mine_mininglimit"] = {}
        mine_limit_updated = False
        for mine_name in self.mineral_chancelist.keys():
            if mine_name not in data["mine_mininglimit"]:
                data["mine_mininglimit"][mine_name] = 500
                mine_limit_updated = True
        if mine_limit_updated:
            common.datawrite(data,"data/mining.json")

        return data


    def roll_random_pickaxe_durability(self) -> int:
        """技能鎬：骰出 10～1000、且為 10 倍數的耐久上限。"""
        return random.randint(1, 100) * 10


    def roll_disaster_pickaxe_skills(self) -> dict:
        """災禍鎬：各技能獨立骰是否取得，並骰出數值／旗標寫入 dict。"""
        skills = {}
        # 增加 1%～40% 獲得額外礦物機率（30% 獨立骰是否取得）
        if random.random() < 0.30:
            skills["bonus_chance_add"] = random.randint(1, 40) / 100.0
        # 觸發額外礦 bonus 時，額外數量再 +1～3（30%）
        if random.random() < 0.30:
            skills["bonus_extra_on_proc"] = random.randint(1, 3)
        # 減少 1～3 秒挖掘等待（20%）
        if random.random() < 0.2:
            skills["dig_time_reduce_sec"] = random.randint(1, 3)
        # 額外礦 bonus 必為該礦場最高價值礦物（20%）
        if random.random() < 0.20:
            skills["bonus_force_highest_value"] = True
        # 每次挖礦有 50% 機率不扣耐久（40% 獨立骰是否擁有此效果）
        if random.random() < 0.40:
            skills["durability_half_skip"] = True
        return skills


    def roll_anchor_pickaxe_skills(self) -> dict:
        """附魔迷你船錨：各技能獨立骰是否取得，並骰出數值／旗標寫入 dict。"""
        skills = {}
        # 增加 20%～100% 獲得額外礦物機率（40%）
        if random.random() < 0.40:
            skills["bonus_chance_add"] = random.randint(20, 100) / 100.0
        # 觸發額外礦 bonus 時額外數量（40% 取得）；內層 70% 為 +1～3、30% 為 +4～8
        if random.random() < 0.4:
            if random.random() < 0.70:
                skills["bonus_extra_on_proc"] = random.randint(1, 3)
            else:
                skills["bonus_extra_on_proc"] = random.randint(4, 8)
        # 減少挖掘等待（30% 取得）；內層 70% 為 1～3 秒、30% 為 4～7 秒
        if random.random() < 0.3:
            if random.random() < 0.70:
                skills["dig_time_reduce_sec"] = random.randint(1, 3)
            else:
                skills["dig_time_reduce_sec"] = random.randint(4, 7)
        # 額外礦 bonus 必為該礦場最高價值礦物（30%）
        if random.random() < 0.30:
            skills["bonus_force_highest_value"] = True
        # 增加收藏品機率（10% 取得）；內層 70% 為 1%～5%、20% 為 6%～10%、10% 為 11%～15%
        if random.random() < 0.1:
            tier = random.random()
            if tier < 0.70:
                skills["collection_chance_add"] = random.randint(1, 5) / 100.0
            elif tier < 0.90:
                skills["collection_chance_add"] = random.randint(6, 10) / 100.0
            else:
                skills["collection_chance_add"] = random.randint(11, 15) / 100.0
        # 每次挖礦有 50% 機率不扣耐久（60%）
        if random.random() < 0.60:
            skills["durability_half_skip"] = True
        return skills


    def roll_skill_pickaxe_instance(self, template: str) -> dict:
        """購買技能鎬時產生一筆背包資料：template、耐久與 skills。"""
        max_health = self.roll_random_pickaxe_durability()
        if template == "災禍鎬":
            skills = self.roll_disaster_pickaxe_skills()
        else:
            skills = self.roll_anchor_pickaxe_skills()
        return {"template": template, "max_health": max_health, "current_health": max_health, "skills": skills}


    def skill_pickaxe_lines_for_embed(self, skills: dict) -> str:
        """把 skills dict 轉成 embed 用多行中文說明。"""
        if not skills:
            return "（無隨機技能）"
        lines = []
        if "bonus_chance_add" in skills:
            lines.append(f"增加**{int(round(skills['bonus_chance_add'] * 100))}%**獲得額外礦物的機率")
        if "bonus_extra_on_proc" in skills:
            lines.append(f"觸發額外礦物時，額外礦物再增加**{skills['bonus_extra_on_proc']}**個")
        if "dig_time_reduce_sec" in skills:
            lines.append(f"減少**{skills['dig_time_reduce_sec']}**秒挖掘時間")
        if skills.get("bonus_force_highest_value"):
            lines.append("額外礦物必為該礦場最高價值礦物")
        if "collection_chance_add" in skills:
            lines.append(f"增加**{int(round(skills['collection_chance_add'] * 100))}%**獲得收藏品的機率")
        if skills.get("durability_half_skip"):
            lines.append("每次挖礦有**50%**機率不消耗耐久")
        return "\n".join(lines)


    def get_active_skills_from_user(self, mining_data: dict, userid: str) -> dict:
        """目前裝備若來自背包格，回傳該格物品的技能 dict；否則空 dict。"""
        slot = mining_data[userid].get("equipped_bag_slot")
        if slot is None:
            return {}
        bag = mining_data[userid]["pickaxe_bag"]
        if slot >= len(bag) or bag[slot] is None:
            return {}
        return bag[slot].get("skills") or {}


    def sync_equipped_pickaxe_to_bag_slot(self, mining_data: dict, userid: str) -> None:
        """把頂層 pickaxe_health／max 寫回目前裝備的背包格，避免資料分歧。"""
        slot = mining_data[userid].get("equipped_bag_slot")
        if slot is None:
            return
        bag = mining_data[userid]["pickaxe_bag"]
        if slot >= len(bag) or bag[slot] is None:
            return
        bag[slot]["current_health"] = mining_data[userid]["pickaxe_health"]
        bag[slot]["max_health"] = mining_data[userid]["pickaxe_maxhealth"]


    def effective_pickaxe_required_level(self, mining_data: dict, userid: str) -> int:
        """目前顯示鎬名對應的「需求等級」（傳統鎬或技能鎬商店表），供 pickaxe_buy 比較。"""
        name = mining_data[userid]["pickaxe"]
        if name in self.pickaxe_list:
            return self.pickaxe_list[name]["需求等級"]
        if name in self.skill_pickaxe_shop:
            return self.skill_pickaxe_shop[name]["需求等級"]
        return 1


    def highest_priced_mineral_in_mine(self, mine_name: str) -> Optional[str]:
        """該礦場掉落表內（排除石頭、機率 0）單價最高之礦物名；同價取字串較大者。"""
        table = self.mineral_chancelist[mine_name]
        best_pair = None
        for mineral, probability in table.items():
            if mineral == "石頭" or probability <= 0:
                continue
            price = self.mineral_pricelist.get(mineral, 0)
            pair = (price, mineral)
            if best_pair is None or pair > best_pair:
                best_pair = pair
        return best_pair[1] if best_pair else None


    def first_empty_pickaxe_bag_index(self, mining_data: dict, userid: str) -> Optional[int]:
        """裝備背包第一個空格子的索引（0-based）；已滿則 None。"""
        bag = mining_data[userid]["pickaxe_bag"]
        for index, entry in enumerate(bag):
            if entry is None:
                return index
        return None


    def restore_legacy_pickaxe_to_top(self, mining_data: dict, userid: str) -> None:
        """卸下技能鎬：還原 legacy_pickaxe_state 到頂層鎬欄位，並清空 equipped_bag_slot。"""
        legacy = mining_data[userid].get("legacy_pickaxe_state")
        if legacy and isinstance(legacy, dict) and "name" in legacy:
            mining_data[userid]["pickaxe"] = legacy["name"]
            mining_data[userid]["pickaxe_health"] = legacy["pickaxe_health"]
            mining_data[userid]["pickaxe_maxhealth"] = legacy["pickaxe_maxhealth"]
        else:
            mining_data[userid]["pickaxe"] = "基本礦鎬"
            mining_data[userid]["pickaxe_health"] = 100
            mining_data[userid]["pickaxe_maxhealth"] = 100
        mining_data[userid]["equipped_bag_slot"] = None


    def parse_mining_bag_drop_arg(self, raw: str) -> Tuple[str, Union[None, int, Tuple[int, int]]]:
        """解析丟棄輸入：all | 單格 1～7 | 區間 "1-3"（數字可含空白）。"""
        text = raw.strip()
        if not text:
            raise ValueError("empty")
        if text.lower() == "all":
            return "all", None
        range_match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", raw)
        if range_match:
            a, b = int(range_match.group(1)), int(range_match.group(2))
            return "range", (min(a, b), max(a, b))
        return "single", int(text)


    @app_commands.command(name = "mining", description = "挖礦!")
    async def mining(self,interaction):
        dig_sleep = 8.0
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            user_data = common.dataload()
            mining_data = self.miningdata_read(userid)
            skills_pre = self.get_active_skills_from_user(mining_data, userid)
            dig_reduce = int(skills_pre.get("dig_time_reduce_sec") or 0)
            # 冷卻與挖掘縮秒同源（下限 1 秒），避免固定 8 秒冷卻與技能縮時不一致
            cooldown_sec = max(1.0, 8.0 - dig_reduce)
            last_mining_ts = float(mining_data[userid].get("mining_cooldown_last") or 0)
            elapsed = time.time() - last_mining_ts
            if last_mining_ts > 0 and elapsed < cooldown_sec:
                wait_sec = max(1, int(cooldown_sec - elapsed + 0.99))
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"挖太快了!請在**{wait_sec}**秒後再試一次。", color=common.bot_error_color), ephemeral=True)
                return

            #確認是否正在重啟保護狀態?
            if time.time() - user_data['restart_time'] <= 15:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="機器人正在重啟，請稍後在試一次。",color=common.bot_error_color))
                return
            user_data['gaming_time'] = time.time()

            #確認礦場是否已挖完?
            if mining_data['mine_mininglimit'][mining_data[userid]['mine']] <= 0:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"**{mining_data[userid]['mine']}**已經挖完了，請明天再來吧，或者移動到其他的礦場。",color=common.bot_error_color))
                return

            #確認礦鎬壞了沒
            if mining_data[userid]["pickaxe_health"] == 0:
                #如果有開啟自動修理
                if mining_data[userid]["autofix"] == True:
                    if user_data[userid]['cake'] < 10:
                        await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的礦鎬已經壞了!而且你的蛋糕也不足以修理礦鎬。",color=common.bot_error_color))
                        return
                    mining_data[userid]['pickaxe_health'] = mining_data[userid]['pickaxe_maxhealth']
                    user_data[userid]["cake"] -= 10
                    self.sync_equipped_pickaxe_to_bag_slot(mining_data, userid)
                else:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的礦鎬已經壞了!",color=common.bot_error_color))
                    return

            dig_sleep = max(0.5, 8.0 - dig_reduce)

            mining_data['mine_mininglimit'][mining_data[userid]['mine']] -= 1
            consume_dura = True
            if skills_pre.get("durability_half_skip") and random.random() < 0.5:
                consume_dura = False
            if consume_dura:
                mining_data[userid]["pickaxe_health"] -= 10
            self.sync_equipped_pickaxe_to_bag_slot(mining_data, userid)
            mining_data[userid]["mining_cooldown_last"] = time.time()
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="正在挖礦中...",color=common.bot_color))
            #寫入檔案防止回溯
            common.datawrite(user_data)
            common.datawrite(mining_data,"data/mining.json")

        await asyncio.sleep(dig_sleep)

        async with common.jsonio_lock:
            #等待時間結束後再次讀取，防止回溯問題
            mining_data = self.miningdata_read(userid)

            #開始抽獎
            reward_probabilities = self.mineral_chancelist[mining_data[userid]["mine"]]
            random_num = random.random()
            current_probability = 0
            for reward, probability in reward_probabilities.items():
                current_probability += probability
                if random_num < current_probability:
                    message = Embed(title="Natalie 挖礦",description=f"你挖到了**{reward}**!",color=common.bot_color)
                    if reward != "石頭":
                        if reward not in mining_data[userid]:
                            mining_data[userid][reward] = 0
                        mining_data[userid][reward] += 1

                        skills = self.get_active_skills_from_user(mining_data, userid)
                        pickaxe_name = mining_data[userid]["pickaxe"]
                        base_prob = 0.0
                        if pickaxe_name == "鑽石鎬":
                            base_prob = 0.1
                        elif pickaxe_name == "不要鎬":
                            base_prob = 0.15
                        base_prob += float(skills.get("bonus_chance_add") or 0)
                        base_prob = min(1.0, base_prob)
                        bonus_extra = int(skills.get("bonus_extra_on_proc") or 0)
                        bonus_qty = 1 + bonus_extra
                        force_highest = bool(skills.get("bonus_force_highest_value"))
                        extra_mineral_type = reward
                        if force_highest:
                            hi = self.highest_priced_mineral_in_mine(mining_data[userid]["mine"])
                            if hi:
                                extra_mineral_type = hi
                        if random.random() < base_prob:
                            if extra_mineral_type not in mining_data[userid]:
                                mining_data[userid][extra_mineral_type] = 0
                            mining_data[userid][extra_mineral_type] += bonus_qty
                            message.description += f"\n你額外獲得了**{bonus_qty}**個**{extra_mineral_type}**!"
                    break

            skills_post = self.get_active_skills_from_user(mining_data, userid)
            collection_base = 0.01 + float(skills_post.get("collection_chance_add") or 0)
            collection_base = min(1.0, collection_base)
            random_num = random.random()
            if random_num < collection_base:
                collection = random.choice(self.collection_list[mining_data[userid]["mine"]])
                if collection not in mining_data[userid]["collections"]:
                    mining_data[userid]["collections"][collection] = 0
                mining_data[userid]["collections"][collection] += 1
                message.add_field(name="找到收藏品!",value=f"獲得**{collection}**!",inline= False)

            random_num = random.random()
            if random_num < 0.05 and (mining_data[userid]["mine"] == "熾熱火炎山" or mining_data[userid]["mine"] == "虛空洞穴" or mining_data[userid]["mine"] == "天境之地"):
                mining_data[userid]["pickaxe_health"] = 0
                self.sync_equipped_pickaxe_to_bag_slot(mining_data, userid)
                message.add_field(name="礦鎬意外損毀!",value="你在挖礦途中不小心把礦鎬弄壞了，需要修理。",inline= False)

            await interaction.edit_original_response(embed=message)
            common.datawrite(mining_data,"data/mining.json")


    @app_commands.command(name = "pickaxe_fix", description = "修理礦鎬(需要10塊蛋糕)")
    async def pickaxe_fix(self,interaction):
        async with common.jsonio_lock:
            #讀資料
            userid = str(interaction.user.id)
            mining_data = self.miningdata_read(userid)
            user_data = common.dataload()
            #如果沒壞
            if mining_data[userid]["pickaxe_health"] != 0:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的礦鎬還沒壞!",color=common.bot_error_color))
                return
            #如果沒蛋糕
            if user_data[userid]["cake"] < 10:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"你的蛋糕不足!(需要**10**塊，你目前只有**{user_data[userid]['cake']}**塊)",color=common.bot_error_color))
                return
            
            #修理要10蛋糕
            user_data[userid]["cake"] -= 10
            mining_data[userid]['pickaxe_health'] = mining_data[userid]['pickaxe_maxhealth']
            self.sync_equipped_pickaxe_to_bag_slot(mining_data, userid)
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="修理完成",color=common.bot_color))
            common.datawrite(user_data)
            common.datawrite(mining_data,"data/mining.json")
        
    @app_commands.command(name = "pickaxe_autofix", description = "自動修理礦鎬設置(預設關閉)")
    async def pickaxe_autofix(self,interaction):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            data = self.miningdata_read(userid)

            if not "autofix" in data[userid] or data[userid]["autofix"] == False:
                data[userid]["autofix"] = True
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="自動修理已開啟。\n在耐久不足時會自動消耗蛋糕進行修理。",color=common.bot_color))
                common.datawrite(data,"data/mining.json")
                return

            if data[userid]["autofix"] == True:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你已經開啟了自動修理礦鎬。",color=common.bot_color),ephemeral=True,view=AutofixButton())

    @app_commands.command(name = "mineral_sell",description="賣出所有礦物")
    async def mineral_sell(self,interaction):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            mining_data = self.miningdata_read(userid)
            message = Embed(title="Natalie 挖礦",color=common.bot_color)
            #計算賣出價
            total_price = 0
            mineral_sellinfo_show = ""
            for mineral, quantity in mining_data[userid].items():
                if mineral in self.mineral_pricelist:
                    total_price += self.mineral_pricelist[mineral] * quantity
                    if quantity != 0:
                        mineral_sellinfo_show += f"{mineral}:**{quantity}**個\n"
            message.add_field(name="你總共賣出了...",value=mineral_sellinfo_show,inline=False)

            #清除礦物
            for mineral in self.mineral_pricelist.keys():
                if mineral in mining_data[userid]:
                    mining_data[userid][mineral] = 0
            common.datawrite(mining_data,"data/mining.json")

            #顯示
            userdata = common.dataload()
            userdata[userid]["cake"] += total_price
            common.datawrite(userdata)
            message.add_field(name=f"你獲得了{total_price}塊{self.bot.get_emoji(common.cake_emoji_id)}",value="",inline=False)
            await interaction.response.send_message(embed=message)

    @app_commands.command(name = "mining_info",description="挖礦資訊")
    async def mining_info(self,interaction):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            mining_data = self.miningdata_read(userid)

        message = Embed(title="Natalie 挖礦",description="指令:\n/mining 挖礦\n/pickaxe_fix 修理礦鎬\n/pickaxe_autofix 自動修理礦鎬\n/mineral_sell 賣出礦物\n/collection_trade 收藏品交易\n/collection_sell 販賣收藏品給Natalie\n/mine 更換礦場\n/pickaxe_buy 購買礦鎬\n/mining_bag 裝備背包\n/mining_bag_use 裝備背包內礦鎬\n/mining_bag_drop 丟棄背包內礦鎬(單格/1-3/all)\n/mining_bag_unequip 卸下技能礦鎬\n/redeem_collection_role 兌換收藏品稱號\n(注意:本指令缺乏測試，兌換前建議\n先使用mining_info留下收藏品資料。)\n/mining_machine_info 關於自動挖礦機",color=common.bot_color)
        equip_slot = mining_data[userid].get("equipped_bag_slot")
        pickaxe_line = f"{mining_data[userid]['pickaxe']}  {mining_data[userid]['pickaxe_health']}/{mining_data[userid]['pickaxe_maxhealth']}"
        if equip_slot is not None:
            pickaxe_line += f"\n（裝備中：背包第 **{equip_slot + 1}** 格）"
            bag_entry = mining_data[userid]["pickaxe_bag"][equip_slot] if equip_slot < len(mining_data[userid]["pickaxe_bag"]) else None
            if bag_entry:
                pickaxe_line += f"\n\n**技能**\n{self.skill_pickaxe_lines_for_embed(bag_entry.get('skills') or {})}"
        message.add_field(name="我的礦鎬",value=pickaxe_line,inline=False)
        message.add_field(name="礦場位置",value=f"{mining_data[userid]['mine']}",inline=False)

        mine_limit_info = ""
        for mine, mininglimit in mining_data["mine_mininglimit"].items():
            mine_limit_info += f"{mine}: **{mininglimit}**\n"
        message.add_field(name="礦場剩餘挖掘量(每天重置)",value=mine_limit_info,inline=False)

        #全部的收藏品列表
        collection_confirm_list = [item for sublist in self.collection_list.values() for item in sublist]
        #用戶的收藏品列表
        collection_confirm_message = ""
        collection_confirm_count = 0
        for item in collection_confirm_list:
            if item in mining_data[userid]['collections'] and mining_data[userid]['collections'][item] > 0:
                collection_confirm_message += f"{item}: {mining_data[userid]['collections'][item]}個\n"
                collection_confirm_count += 1
        message.add_field(name=f"擁有收藏品 {collection_confirm_count}/{len(collection_confirm_list)}",value=f"{collection_confirm_message}",inline=False)
        await interaction.response.send_message(embed=message)
        
    @app_commands.command(name = "collection_trade",description="與其他玩家交易收藏品")
    @app_commands.describe(collection_name="要販賣的收藏品名稱",price="要販賣的價格(蛋糕)")
    @app_commands.rename(collection_name="名稱",price="價格")
    @app_commands.checks.cooldown(1, 60)
    async def collection_trade(self,interaction,collection_name: str,price: int):
        userid = str(interaction.user.id)
        mining_data = self.miningdata_read(userid)

        if price <= 0:
            await interaction.response.send_message(embed=Embed(title='Natalie 挖礦',description="錯誤:請輸入有效的價格",color=common.bot_error_color))
            return

        #全部的收藏品列表
        collection_confirm_list = [item for sublist in self.collection_list.values() for item in sublist]
        #如果沒有在收藏品清單
        if collection_name not in collection_confirm_list:
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="錯誤:不存在的收藏品。",color=common.bot_error_color))
            return

        #如果該收藏品不在用戶收藏品清單內或數量=0
        if collection_name not in mining_data[userid]["collections"] or mining_data[userid]["collections"][collection_name] == 0:
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"錯誤:你沒有**{collection_name}**。",color=common.bot_error_color))
            return

        #準備發送交易訊息
        message = Embed(title="Natalie 挖礦",description=f"<@{userid}>正在販賣一項收藏品，有興趣的話請點擊下方的購買按鈕!\n交易提案有效時間為60秒。",color=common.bot_color)
        message.add_field(name="收藏品",value=f"**{collection_name}**",inline=False)
        message.add_field(name="價格",value=f"**{price}**塊蛋糕",inline=False)
        await interaction.response.send_message(embed=message,view=CollectionTradeButton(selluser=interaction,collection_name=collection_name,price=price,client=self.bot))

    @app_commands.command(name = "collection_sell",description="販賣收藏品給Natalie(每個1000塊蛋糕)")
    @app_commands.describe(collection_name="要販賣的收藏品名稱")
    @app_commands.rename(collection_name="名稱")
    async def collection_sell(self,interaction,collection_name: str):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            mining_data = self.miningdata_read(userid)
            user_data = common.dataload()

            #全部的收藏品列表
            collection_confirm_list = [item for sublist in self.collection_list.values() for item in sublist]
            #如果沒有在收藏品清單
            if collection_name not in collection_confirm_list:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="錯誤:不存在的收藏品。",color=common.bot_error_color))
                return
            
            #如果該收藏品不在用戶收藏品清單內或數量=0
            if collection_name not in mining_data[userid]["collections"] or mining_data[userid]["collections"][collection_name] == 0:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"錯誤:你沒有**{collection_name}**。",color=common.bot_error_color))
                return
            
            mining_data[userid]["collections"][collection_name] -= 1
            user_data[userid]['cake'] += 1000
            common.datawrite(mining_data,'data/mining.json')
            common.datawrite(user_data)

        await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"你賣出了**1**個**{collection_name}**。\n獲得**1000**塊{self.bot.get_emoji(common.cake_emoji_id)}",color=common.bot_color))


    @app_commands.command(name = "mine",description="更換礦場")
    @app_commands.describe(choices="要更換的礦場")
    @app_commands.rename(choices="選擇礦場")
    @app_commands.choices(choices=[
        app_commands.Choice(name="森林礦坑  1等", value="森林礦坑"),
        app_commands.Choice(name="荒野高原  10等", value="荒野高原"),
        app_commands.Choice(name="蛋糕仙境  18等", value="蛋糕仙境"),
        app_commands.Choice(name="永世凍土  26等", value="永世凍土"),
        app_commands.Choice(name="熾熱火炎山(高風險)  34等", value="熾熱火炎山"),
        app_commands.Choice(name="虛空洞穴(高風險)  42等", value="虛空洞穴"),
        app_commands.Choice(name="天境之地(高風險)  70等", value="天境之地")
        ])
    async def mine(self,interaction,choices: app_commands.Choice[str]):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            mining_data = self.miningdata_read(userid)
            userlevel = common.LevelSystem().read_info(userid)

            #確認是否選擇了目前待的礦場
            if choices.value == mining_data[userid]['mine']:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"你目前已經在**{choices.value}**。",color=common.bot_error_color))
                return
            
            #確認等級是否足夠?
            if userlevel.level < self.mine_levellimit[choices.value]:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"等級不足，**{choices.value}**礦場需要**{self.mine_levellimit[choices.value]}**等",color=common.bot_error_color))
                return

            mining_data[userid]['mine'] = choices.value
            common.datawrite(mining_data,"data/mining.json")
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"已移動到**{choices.value}**礦場，當前礦場剩餘挖礦次數:**{mining_data['mine_mininglimit'][choices.value]}**",color=common.bot_color))

    @app_commands.command(name = "pickaxe_buy",description="購買礦鎬")
    @app_commands.describe(choices="要購買的礦鎬")
    @app_commands.rename(choices="選擇礦鎬")
    @app_commands.choices(choices=[
        app_commands.Choice(name="石鎬  耐久:200 需要6等 $500", value="石鎬"),
        app_commands.Choice(name="鐵鎬  耐久:400 需要12等 $2000", value="鐵鎬"),
        app_commands.Choice(name="鑽石鎬  耐久:650 需要18等 $3000", value="鑽石鎬"),
        app_commands.Choice(name="不要鎬  耐久:1000 需要25等 $5000", value="不要鎬"),
        app_commands.Choice(name="災禍鎬(隨機技能) 耐久10~1000 50等 $10000", value="災禍鎬"),
        app_commands.Choice(name="附魔迷你船錨(隨機技能) 耐久10~1000 64等 $20000", value="附魔迷你船錨"),
        ])
    async def pickaxe_buy(self,interaction,choices: app_commands.Choice[str]):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            user_data = common.dataload()
            mining_data = self.miningdata_read(userid)
            value = choices.value

            if value in self.skill_pickaxe_shop:
                meta = self.skill_pickaxe_shop[value]
                if meta["需求等級"] > user_data[userid]["level"]:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的等級不足以購買此礦鎬!",color=common.bot_error_color))
                    return
                if user_data[userid]["cake"] < meta["價格"]:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"你沒有足夠的蛋糕購買此礦鎬!(購買需要**{meta['價格']}**，你只有**{user_data[userid]['cake']}**)。",color=common.bot_error_color))
                    return
                free_index = self.first_empty_pickaxe_bag_index(mining_data, userid)
                if free_index is None:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="裝備背包已滿(7格)，請先使用 `/mining_bag_drop` 丟棄礦鎬後再購買。",color=common.bot_error_color))
                    return
                user_data[userid]["cake"] -= meta["價格"]
                instance = self.roll_skill_pickaxe_instance(value)
                mining_data[userid]["pickaxe_bag"][free_index] = instance
                skill_text = self.skill_pickaxe_lines_for_embed(instance["skills"])
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"購買成功！**{value}**已放入裝備背包第 **{free_index + 1}** 格。\n耐久 **{instance['current_health']}/{instance['max_health']}**\n\n{skill_text}",color=common.bot_color))
                common.datawrite(user_data)
                common.datawrite(mining_data,"data/mining.json")
                return

            if mining_data[userid]["pickaxe"] == value:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你已經擁有此礦鎬了!",color=common.bot_error_color))
                return
            if self.pickaxe_list[value]['需求等級'] > user_data[userid]['level']:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的等級不足以購買此礦鎬!",color=common.bot_error_color))
                return
            current_tier = self.effective_pickaxe_required_level(mining_data, userid)
            if self.pickaxe_list[value]['需求等級'] < current_tier:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你不能購買更劣質的礦鎬!",color=common.bot_error_color))
                return
            if user_data[userid]['cake'] < self.pickaxe_list[value]['價格']:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"你沒有足夠的蛋糕購買此礦鎬!(購買需要**{self.pickaxe_list[value]['價格']}**，你只有**{user_data[userid]['cake']}**)。",color=common.bot_error_color))
                return

            user_data[userid]['cake'] -= self.pickaxe_list[value]['價格']
            mining_data[userid]["equipped_bag_slot"] = None
            mining_data[userid]["legacy_pickaxe_state"] = None
            mining_data[userid]["pickaxe"] = value
            mining_data[userid]['pickaxe_maxhealth'] = self.pickaxe_list[value]['耐久度']
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"購買成功! 你現在擁有了**{value}**。",color=common.bot_color))
            common.datawrite(user_data)
            common.datawrite(mining_data,"data/mining.json")

    @app_commands.command(name = "mining_bag", description = "查看裝備背包（技能礦鎬）")
    async def mining_bag(self, interaction):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            mining_data = self.miningdata_read(userid)
        message = Embed(title="Natalie 挖礦｜裝備背包", description="共 7 格。使用 `/mining_bag_use` 裝備、`/mining_bag_drop` 丟棄（單格／`1-3`／`all`）、`/mining_bag_unequip` 卸下技能鎬。", color=common.bot_color)
        equipped = mining_data[userid].get("equipped_bag_slot")
        for index in range(self.pickaxe_bag_size):
            entry = mining_data[userid]["pickaxe_bag"][index]
            slot_label = index + 1
            if entry is None:
                field_name = f"[{slot_label}] （空）"
                field_value = "—"
            else:
                name = entry.get("template", "未知")
                cur = entry.get("current_health", 0)
                mx = entry.get("max_health", 0)
                equip_tag = " 裝備中" if equipped == index else ""
                field_name = f"[{slot_label}] {name}  {cur}/{mx}{equip_tag}"
                field_value = self.skill_pickaxe_lines_for_embed(entry.get("skills") or {})
            message.add_field(name=field_name, value=field_value, inline=False)
        await interaction.response.send_message(embed=message)

    @app_commands.command(name = "mining_bag_drop", description = "丟棄裝備背包內的技能礦鎬")
    @app_commands.describe(slot="允許單個、區間如 1-3、或 all（會保留裝備中的道具）")
    @app_commands.rename(slot="編號")
    async def mining_bag_drop(self, interaction, slot: str):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            mining_data = self.miningdata_read(userid)
            try:
                mode, payload = self.parse_mining_bag_drop_arg(slot)
            except (ValueError, TypeError):
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description="格式錯誤。請輸入單格 **1～7**、區間如 **1-3**，或 **all**。", color=common.bot_error_color))
                return

            bag = mining_data[userid]["pickaxe_bag"]
            equipped_idx = mining_data[userid].get("equipped_bag_slot")

            if mode == "all":
                dropped_slots = []
                for index in range(self.pickaxe_bag_size):
                    if index == equipped_idx:
                        continue
                    if bag[index] is not None:
                        bag[index] = None
                        dropped_slots.append(str(index + 1))
                common.datawrite(mining_data, "data/mining.json")
                if not dropped_slots:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description="沒有可丟棄的礦鎬（其餘空格或僅剩裝備中）。", color=common.bot_error_color))
                    return
                slots_text = "、".join(dropped_slots)
                equip_hint = f"\n（已保留裝備中第 **{equipped_idx + 1}** 格）" if equipped_idx is not None else ""
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"已丟棄 **{len(dropped_slots)}** 把礦鎬（第 **{slots_text}** 格）。{equip_hint}", color=common.bot_color))
                return

            if mode == "single":
                slot_num = payload
                if slot_num < 1 or slot_num > self.pickaxe_bag_size:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"格子編號須為 **1**～**{self.pickaxe_bag_size}**。", color=common.bot_error_color))
                    return
                idx = slot_num - 1
                if equipped_idx == idx:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description="無法丟棄**裝備中**的礦鎬，請先 `/mining_bag_unequip` 卸下。", color=common.bot_error_color))
                    return
                if bag[idx] is None:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description="該格沒有物品。", color=common.bot_error_color))
                    return
                bag[idx] = None
                common.datawrite(mining_data, "data/mining.json")
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"已丟棄背包第 **{slot_num}** 格的礦鎬。", color=common.bot_color))
                return

            # range
            lo, hi = payload
            if lo < 1 or hi > self.pickaxe_bag_size or lo > hi:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"區間須在 **1**～**{self.pickaxe_bag_size}** 內，且左不大於右。", color=common.bot_error_color))
                return
            if equipped_idx is not None:
                equip_num = equipped_idx + 1
                if lo <= equip_num <= hi:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"區間內包含**裝備中**的第 **{equip_num}** 格，無法丟棄。請先卸下或改用 **all**（會保留裝備格）。", color=common.bot_error_color))
                    return
            dropped_slots = []
            for slot_num in range(lo, hi + 1):
                idx = slot_num - 1
                if bag[idx] is not None:
                    bag[idx] = None
                    dropped_slots.append(str(slot_num))
            common.datawrite(mining_data, "data/mining.json")
            if not dropped_slots:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description="該區間內沒有礦鎬可丟棄。", color=common.bot_error_color))
                return
            slots_text = "、".join(dropped_slots)
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"已丟棄 **{len(dropped_slots)}** 把礦鎬（第 **{slots_text}** 格）。", color=common.bot_color))

    @app_commands.command(name = "mining_bag_use", description = "裝備裝備背包第 N 格的礦鎬")
    @app_commands.describe(slot="格子編號 1~7")
    @app_commands.rename(slot="格子編號")
    async def mining_bag_use(self, interaction, slot: int):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            mining_data = self.miningdata_read(userid)
            if slot < 1 or slot > self.pickaxe_bag_size:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"格子編號須為 **1**～**{self.pickaxe_bag_size}**。", color=common.bot_error_color))
                return
            idx = slot - 1
            entry = mining_data[userid]["pickaxe_bag"][idx]
            if entry is None:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description="該格沒有物品。", color=common.bot_error_color))
                return
            if mining_data[userid].get("equipped_bag_slot") is not None:
                self.sync_equipped_pickaxe_to_bag_slot(mining_data, userid)
            prev_slot = mining_data[userid].get("equipped_bag_slot")
            if prev_slot is None and mining_data[userid].get("legacy_pickaxe_state") is None:
                mining_data[userid]["legacy_pickaxe_state"] = {
                    "name": mining_data[userid]["pickaxe"],
                    "pickaxe_health": mining_data[userid]["pickaxe_health"],
                    "pickaxe_maxhealth": mining_data[userid]["pickaxe_maxhealth"],
                }
            mining_data[userid]["equipped_bag_slot"] = idx
            mining_data[userid]["pickaxe"] = entry["template"]
            mining_data[userid]["pickaxe_maxhealth"] = entry["max_health"]
            mining_data[userid]["pickaxe_health"] = entry["current_health"]
            common.datawrite(mining_data, "data/mining.json")
        await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description=f"已裝備背包第 **{slot}** 格的 **{entry['template']}**。", color=common.bot_color))

    @app_commands.command(name = "mining_bag_unequip", description = "卸下技能礦鎬，還原為先前使用的傳統礦鎬")
    async def mining_bag_unequip(self, interaction):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            mining_data = self.miningdata_read(userid)
            if mining_data[userid].get("equipped_bag_slot") is None:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description="你目前沒有裝備背包內的技能礦鎬。", color=common.bot_error_color))
                return
            self.restore_legacy_pickaxe_to_top(mining_data, userid)
            common.datawrite(mining_data, "data/mining.json")
        await interaction.response.send_message(embed=Embed(title="Natalie 挖礦", description="已卸下技能礦鎬。", color=common.bot_color))

    @app_commands.command(name = "redeem_collection_role",description="兌換收藏品稱號(需要每種收藏品各一個，兌換後會消耗掉)")
    async def redeem_collection_role(self,interaction):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            mining_data = self.miningdata_read(userid)
            #全部的收藏品列表
            collection_confirm_list = [item for sublist in self.collection_list.values() for item in sublist]
            #用戶收藏品
            user_collections = mining_data[userid]["collections"]
            #缺少的收藏品清單
            missing_collections = [item for item in collection_confirm_list if item not in user_collections or user_collections[item] < 1]
            if missing_collections:
                await interaction.response.send_message(embed=Embed(title="兌換收藏品稱號", description=f"兌換失敗:你還缺**{len(missing_collections)}**種收藏品。", color=common.bot_error_color))
                return
            for item in collection_confirm_list:
                user_collections[item] -= 1

            #允許獲得稱號
            mining_data[userid]["collections"] = user_collections
            common.datawrite(mining_data,"data/mining.json")
            #獲取稱號
            await interaction.user.add_roles(interaction.guild.get_role(1070206894288928798))
            await interaction.response.send_message(embed=Embed(title="兌換收藏品稱號",description="成功兌換稱號!",color=common.bot_color))

    @app_commands.command(name = "mining_machine_info",description="自動挖礦機資訊...")
    async def mining_machine_info(self,interaction):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            mining_data = self.miningdata_read(userid)
        message = Embed(title="自動挖礦機",description="你可以透過購買自動挖礦機來挖掘礦物，每3小時會挖掘一次，挖到的礦物會直接列入玩家礦物清單。\n注意!!由於挖礦機火力太強，會破壞掉珍貴的收藏品，因此自動挖掘時'不會'獲得任何收藏品",color=common.bot_color)
        message.add_field(name="目前持有的挖礦機數量",value=f"**{mining_data[userid]['machine_amount']}**",inline=False)
        if (mining_data[userid]['machine_amount'])*1000 == 0:
            message.add_field(name="購買價格 ***(第一台挖礦機為免費)***",value=f"**{(mining_data[userid]['machine_amount'])*1000}** (使用`/mining_machine_buy`購買挖礦機)",inline=False)
        else:
            message.add_field(name="購買價格",value=f"**{(mining_data[userid]['machine_amount'])*1000}** (使用`/mining_machine_buy`購買挖礦機)",inline=False)
        message.add_field(name="挖礦機所在的礦場",value=f"**{mining_data[userid]['machine_mine']}** (使用`/mining_machine_mine`更換礦場)",inline=False)
        await interaction.response.send_message(embed=message)

    @app_commands.command(name = "mining_machine_mine",description="選擇自動挖礦機的礦場")
    @app_commands.describe(choices="要更換的礦場")
    @app_commands.rename(choices="選擇礦場")
    @app_commands.choices(choices=[
        app_commands.Choice(name="森林礦坑  1等", value="森林礦坑"),
        app_commands.Choice(name="荒野高原  10等", value="荒野高原"),
        app_commands.Choice(name="蛋糕仙境  18等", value="蛋糕仙境"),
        app_commands.Choice(name="永世凍土  26等", value="永世凍土"),
        app_commands.Choice(name="熾熱火炎山(高風險)  34等", value="熾熱火炎山"),
        app_commands.Choice(name="虛空洞穴(高風險)  42等", value="虛空洞穴"),
        app_commands.Choice(name="天境之地(高風險)  70等", value="天境之地")
        ])
    async def mining_machine_mine(self,interaction,choices: app_commands.Choice[str]):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            mining_data = self.miningdata_read(userid)
            userlevel = common.LevelSystem().read_info(userid)

            #確認是否選擇了目前待的礦場
            if choices.value == mining_data[userid]['machine_mine']:
                await interaction.response.send_message(embed=Embed(title="自動挖礦機",description=f"你的挖礦機目前已經在**{choices.value}**。",color=common.bot_error_color))
                return

            #確認等級是否足夠?
            if userlevel.level < self.mine_levellimit[choices.value]:
                await interaction.response.send_message(embed=Embed(title="自動挖礦機",description=f"等級不足，**{choices.value}**礦場需要**{self.mine_levellimit[choices.value]}**等",color=common.bot_error_color))
                return
            
            mining_data[userid]['machine_mine'] = choices.value
            common.datawrite(mining_data,"data/mining.json")
            await interaction.response.send_message(embed=Embed(title="自動挖礦機",description=f"礦機已移動到**{choices.value}**礦場。",color=common.bot_color))

    @app_commands.command(name = "mining_machine_buy",description="購買挖礦機")
    async def mining_machine_buy(self,interaction):
        userid = str(interaction.user.id)
        async with common.jsonio_lock:
            data = common.dataload()
            mining_data = self.miningdata_read(userid)
            cake_emoji = self.bot.get_emoji(common.cake_emoji_id)
            price = mining_data[userid]['machine_amount'] *1000

            #蛋糕不足
            if data[userid]['cake'] < price:
                await interaction.response.send_message(embed=Embed(title="自動挖礦機",description=f"{cake_emoji}不足，購買挖礦機需要**{price}**塊{cake_emoji}，而你只有**{data[userid]['cake']}**塊{cake_emoji}",color=common.bot_error_color))
                return
            #暫時性的限制:目前一位使用者最多購買10台
            if mining_data[userid]['machine_amount'] >= 10:
                await interaction.response.send_message(embed=Embed(title="自動挖礦機",description="你目前只能擁有最多**10**台挖礦機。\n是否開放上限請等待後續更新。",color=common.bot_error_color))
                return
            
            data[userid]['cake'] -= price
            mining_data[userid]['machine_amount'] += 1
            common.datawrite(data)
            common.datawrite(mining_data,"data/mining.json")
            await interaction.response.send_message(embed=Embed(title="自動挖礦機",description=f"購買完成，你現在擁有**{mining_data[userid]['machine_amount']}**台挖礦機。",color=common.bot_color))



    @mining.error
    @collection_trade.error
    async def on_cooldown(self,interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"輸入太快了，妹妹頂不住!請在{int(error.retry_after)}秒後再試一次。",color=common.bot_error_color), ephemeral=True)

class BlackJack(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.deck = [{"2": 2}, {"3": 3}, {"4": 4}, {"5": 5}, {"6": 6}, {"7": 7}, {"8": 8}, {"9": 9}, {"10": 10}, {"J": 10}, {"Q": 10}, {"K": 10}, {"A": 11}] * 4
        # 邊注例牌賠率(利潤倍數，派彩時另加還原邊注本金)
        self.side_bet_payout = {
            "straight": 12,
            "trips": 35,
            "bj_straight_678": 60,
            "bj_trips_7": 85,
        }
        self.side_bet_labels = {
            "straight": "順子",
            "trips": "三條",
            "bj_straight_678": "21點順子(6、7、8)",
            "bj_trips_7": "21點三條(7、7、7)",
        }

    #加牌
    def deal_card(self,interaction,playing_deck, recipient):
        card = playing_deck.pop()
        recipient.append(card)

    #計算手牌點數
    def calculate_point(self,player_cards) -> int:
        hand_points = sum(list(card.values())[0] for card in player_cards)
        for card in player_cards:
            if hand_points > 21 and 11 in card.values():
                hand_points -= 10
        return hand_points

    #莊家是否為兩張牌的自然21點(用於保險結算)
    def dealer_natural_blackjack(self, bot_cards) -> bool:
        return len(bot_cards) == 2 and self.calculate_point(bot_cards) == 21

    #顯示牌面
    def show_cards(self,player_cards):
        return '、'.join([list(card.keys())[0] for card in player_cards])

    # 從單張牌 dict 取出牌面字串(如 "7"、"K")
    def card_rank_name(self, card) -> str:
        return list(card.keys())[0]

    # 順子判定用：把牌面轉成連續整數；A 可當 1(A-2-3)或 14(Q-K-A)
    def rank_straight_values(self, rank: str) -> list[int]:
        if rank == "A":
            return [1, 14]
        if rank == "J":
            return [11]
        if rank == "Q":
            return [12]
        if rank == "K":
            return [13]
        # "2"~"10" 對應點數序
        return [int(rank)]

    # 三張牌面是否為順子(不含三條)；窮舉 A 的兩種取值後檢查是否連號
    def is_three_card_straight_ranks(self, rank_a: str, rank_b: str, rank_c: str) -> bool:
        if rank_a == rank_b == rank_c:
            return False
        for combo in itertools.product(
            self.rank_straight_values(rank_a),
            self.rank_straight_values(rank_b),
            self.rank_straight_values(rank_c),
        ):
            sorted_vals = sorted(combo)
            # 三個數字遞增且相鄰差皆為 1
            if sorted_vals[2] - sorted_vals[1] == 1 and sorted_vals[1] - sorted_vals[0] == 1:
                return True
        return False

    # 莊家第一張 + 玩家兩張是否符合邊注例牌；回傳類別鍵或 None
    def side_bet_pattern(self, dealer_first_card, player_cards) -> Optional[str]:
        dealer_rank = self.card_rank_name(dealer_first_card)
        rank_p0 = self.card_rank_name(player_cards[0])
        rank_p1 = self.card_rank_name(player_cards[1])
        three = (dealer_rank, rank_p0, rank_p1)
        if dealer_rank == "7" and rank_p0 == "7" and rank_p1 == "7":
            return "bj_trips_7"
        if set(three) == {"6", "7", "8"}:
            return "bj_straight_678"
        if dealer_rank == rank_p0 == rank_p1:
            return "trips"
        if self.is_three_card_straight_ranks(dealer_rank, rank_p0, rank_p1):
            return "straight"
        return None

    @staticmethod
    def side_bet_loss_line(side_bet_amount: int, cake_emoji) -> str:
        if side_bet_amount <= 0:
            return ""
        return f"\n你失去了**{side_bet_amount}**塊{cake_emoji}(邊注)"

    #顯示勝率跟場數(給embed footer以及leaderboard用的)
    def win_rate_show(self, userid: str, data: dict | None = None) -> str:
        if data is None:
            data = common.dataload()
        if data[userid]["blackjack_round"] == 0:
            return f"你的勝率:未知 總場數:{data[userid]['blackjack_round']}"
        else:
            win_rate = (data[userid]['blackjack_win_rate'] + data[userid]['blackjack_tie'] * 0.5)/data[userid]['blackjack_round']
            return f"你的勝率:{win_rate:.1%} 總場數:{data[userid]['blackjack_round']}"



    @app_commands.command(name = "blackjack", description = "21點!")
    @app_commands.describe(
        bet="要下多少賭注?(支援all、half以及輸入蛋糕數量)",
        side_bet="邊注：三張例牌(順子/三條/21點順子/21點三條)額外賭注，留空表示不玩邊注",
    )
    @app_commands.rename(bet="賭注", side_bet="邊注")
    async def blackjack(self, interaction, bet: str, side_bet: Optional[str] = None):
        #增加回應推遲，避免來不及發送embed造成遊戲狀態鎖死的問題
        await interaction.response.defer()
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            cake_emoji = self.bot.get_emoji(common.cake_emoji_id)
            
            #檢查上一局遊戲有沒有玩完
            if "blackjack_playing" in data[userid] and data[userid]["blackjack_playing"] == True:
                await interaction.followup.send(embed=Embed(title="Natalie 21點",description="你現在有進行中的遊戲!",color=common.bot_error_color))
                return

            #檢查要下注的蛋糕數據
            main_bet_is_all = False
            #下全部
            if bet == "all":
                main_bet_is_all = True
                if data[userid]['cake'] >= 1:
                    bet = data[userid]['cake']
                else:
                    await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"你現在沒有任何{cake_emoji}，無法下注!",color=common.bot_error_color))
                    return
            #下一半
            elif bet == "half":
                if data[userid]['cake'] >= 2:
                    bet = data[userid]['cake'] // 2
                else:
                    await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"你的{cake_emoji}不足(至少需2個{cake_emoji})，無法下注!",color=common.bot_error_color))
                    return
            #user自己輸入數量
            elif bet.isdigit() and int(bet) >= 1:
                bet = int(bet)
            else:
                await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"無效的數據。(輸入想賭注的{cake_emoji}數量，或者輸入all下注全部的{cake_emoji})",color=common.bot_error_color))
                return

            side_bet_amount = 0
            if side_bet is not None and str(side_bet).strip() != "":
                sb = str(side_bet).strip()
                if main_bet_is_all:
                    await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"主注已使用 all 時無法再下邊注。",color=common.bot_error_color))
                    return
                if sb == "all":
                    await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"邊注不支援 all，請輸入數字、half 或留空。",color=common.bot_error_color))
                    return
                if sb == "half":
                    if bet < 2:
                        await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"主注至少需 2 個{cake_emoji}才能使用邊注 half。",color=common.bot_error_color))
                        return
                    side_bet_amount = bet // 2
                elif sb.isdigit() and int(sb) >= 1:
                    side_bet_amount = int(sb)
                else:
                    await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"無效的邊注。(輸入{cake_emoji}數量、half，或留空不玩邊注)",color=common.bot_error_color))
                    return

            #檢查蛋糕是否足夠
            total_stake = bet + side_bet_amount
            if data[userid]["cake"] < total_stake:
                await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"{cake_emoji}不足，無法下注!(主注+邊注共需**{total_stake}**)",color=common.bot_error_color))
                return
            data[userid]["cake"] -= total_stake

            #檢查玩家是否有勝場資料
            # win rate = 勝場數
            # round = 總遊戲場數
            # tie = 平手場數
            if "blackjack_tie" not in data[userid]:
                data[userid]["blackjack_win_rate"] = 0
                data[userid]["blackjack_round"] = 0
                data[userid]["blackjack_tie"] = 0

            #初始化牌堆
            playing_deck = self.deck.copy()
            random.shuffle(playing_deck)
            player_cards = []
            bot_cards = []

            #發牌，玩家莊家各兩張
            self.deal_card(self, playing_deck, player_cards)
            self.deal_card(self, playing_deck, bot_cards)
            self.deal_card(self, playing_deck, player_cards)
            self.deal_card(self, playing_deck, bot_cards)
            #隱藏莊家的第二張牌(蓋牌)
            display_bot_cards = f"{list(bot_cards[0].keys())[0]}、?"
            display_bot_points = f"{sum(bot_cards[0].values())} + ?"

            message = Embed(title="Natalie 21點",description="",color=common.bot_color)
            message.add_field(name=f"你的手牌點數:**{self.calculate_point(player_cards)}**",value=f"{self.show_cards(player_cards)}",inline=False)
            message.add_field(name=f"Natalie的手牌點數:**{display_bot_points}**",value=f"{display_bot_cards}",inline=False)
            if side_bet_amount > 0:
                pattern = self.side_bet_pattern(bot_cards[0], player_cards)
                if pattern is not None:
                    mult = self.side_bet_payout[pattern]
                    label = self.side_bet_labels[pattern]
                    side_return = side_bet_amount * (1 + mult)
                    data[userid]["cake"] += bet * 2 + side_return
                    data[userid]["blackjack_win_rate"] += 1
                    data[userid]["blackjack_round"] += 1
                    common.datawrite(data)
                    message.add_field(
                        name="結果",
                        value=(
                            f"**例牌邊注命中！**\n"
                            f"牌型: **{label}**\n"
                            f"你獲得了**{bet * 2}**塊{cake_emoji}(主注)\n"
                            f"你獲得了**{side_return}**塊{cake_emoji}（邊注×{mult}）\n"
                            f"你現在有**{data[userid]['cake']}**塊{cake_emoji}"
                        ),
                        inline=False,
                    )
                    message.set_footer(text=self.win_rate_show(userid))
                    await interaction.followup.send(embed=message)
                    return
            #玩家如果是blackjack(持有兩張牌且點數剛好為21)
            if self.calculate_point(player_cards) == 21:
                data[userid]['cake'] += int(bet + (bet*1.5))
                message.add_field(name="結果",value=f"**BlackJack!**\n你獲得了**{int(bet*1.5)}**塊{cake_emoji}(blackjack! x 1.5){BlackJack.side_bet_loss_line(side_bet_amount, cake_emoji)}\n你現在有**{data[userid]['cake']}**塊{cake_emoji}",inline=False)
                data[userid]["blackjack_win_rate"] += 1
                data[userid]["blackjack_round"] += 1
                common.datawrite(data)
                message.set_footer(text=self.win_rate_show(userid))
                await interaction.followup.send(embed=message)
                return
            
            data[userid]["blackjack_playing"] = True
            common.datawrite(data)
        #選項給予
        if side_bet_amount > 0:
            message.description = f"本局邊注:**{side_bet_amount}**塊{cake_emoji}"
        message.set_footer(text=self.win_rate_show(userid))
        cake_after_bet = data[userid]['cake']
        await interaction.followup.send(embed=message,view = BlackJackButton(user=interaction,bet=bet,player_cards=player_cards,bot_cards=bot_cards,playing_deck=playing_deck,client=self.bot,display_bot_points=display_bot_points,display_bot_cards=display_bot_cards,cake_after_bet=cake_after_bet,side_bet_amount=side_bet_amount,cake_emoji=cake_emoji))


    @app_commands.command(name = "blackjack_leaderboard", description = "21點勝率排行榜")
    async def blackjack_leaderboard(self,interaction):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            #檢查玩家是否有勝場資料
            # win rate = 勝場數
            # round = 總遊戲場數
            # tie = 平手場數
            if "blackjack_tie" not in data[userid]:
                data[userid]["blackjack_win_rate"] = 0
                data[userid]["blackjack_round"] = 0
                data[userid]["blackjack_tie"] = 0
                common.datawrite(data)
        # 過濾有"blackjack_round" >=50 的玩家，並計算勝率
        players = []
        for user_id, user_data in data.items():
            if isinstance(user_data, dict) and "blackjack_round" in user_data and user_data["blackjack_round"] >= 50:
                win_rate = (user_data["blackjack_win_rate"] + user_data["blackjack_tie"] * 0.5) / user_data["blackjack_round"]
                players.append({"user_id": user_id, "win_rate": win_rate, "round": user_data["blackjack_round"]})

        # 根據勝率排序
        players.sort(key=lambda x: x["win_rate"], reverse=True)

        # 取前五名玩家
        top_players = players[:5]
        message = ""
        # 輸出結果
        for i, player in enumerate(top_players):
            user_object = self.bot.get_user(int(player['user_id']))
            message += f"{i+1}.{user_object.display_name} 勝率:**{player['win_rate']:.1%}** 總場數:**{player['round']}**\n"

        #指令輸入者的勝率(如果沒有玩過則顯示0)
        if data[userid]["blackjack_round"] == 0:
            interaction_user_win_rate = 0
        else:
            interaction_user_win_rate = (data[userid]["blackjack_win_rate"] + data[userid]["blackjack_tie"] *0.5) / data[userid]["blackjack_round"]
        await interaction.response.send_message(embed=Embed(title="21點勝率排行榜",description=f"注意:需要遊玩至少50場才會記錄至排行榜。\n{message}\n你的勝率為:**{interaction_user_win_rate:.1%}** 總場數:**{data[userid]['blackjack_round']}**",color=common.bot_color))
        

class BlackJackButton(discord.ui.View):
    def __init__(self, *,timeout= 120,user,bet,player_cards,bot_cards,playing_deck,client,display_bot_points,display_bot_cards,cake_after_bet,side_bet_amount=0,cake_emoji=None):
        super().__init__(timeout=timeout)
        self.command_interaction = user
        self.bet = bet
        self.side_bet_amount = side_bet_amount
        self.player_cards = player_cards
        self.bot_cards = bot_cards
        self.playing_deck = playing_deck
        self.bot = client
        self.display_bot_points = display_bot_points
        self.display_bot_cards = display_bot_cards
        self.cake_emoji = cake_emoji if cake_emoji is not None else self.bot.get_emoji(common.cake_emoji_id)
        self.insurance_bet_amount = bet // 2
        self.insurance_purchased = False
        self.player_moved_for_insurance = False
        self.configure_insurance_button_state(cake_after_bet)

    def configure_insurance_button_state(self, cake_balance: int):
        """配置保險按鈕的狀態

        Args:
            cake_balance (int): 玩家目前的蛋糕數量
        """
        ib = self.insurance_bet_amount
        dealer_ace_up = list(self.bot_cards[0].keys())[0] == "A"
        can_buy = dealer_ace_up and self.bet >= 2 and ib >= 1 and cake_balance >= ib and not self.player_moved_for_insurance
        if self.insurance_purchased:
            self.insurance_button.label = "已購買保險"
            self.insurance_button.disabled = True
            return
        if can_buy:
            self.insurance_button.label = "購買保險"
            self.insurance_button.disabled = False
        else:
            self.insurance_button.label = "保險:不可購買"
            self.insurance_button.disabled = True

    def side_bet_description(self) -> Optional[str]:
        if self.side_bet_amount <= 0:
            return None
        return f"本局邊注:**{self.side_bet_amount}**塊{self.cake_emoji}"

    def resolve_insurance_payout(self, data, userid: str, dealer_natural: bool):
        """結算保險的賠償

        Args:
            data (dict): 玩家資料
            userid (str): 玩家ID
            dealer_natural (bool): 莊家是否為兩張牌的自然21點
        """
        if not self.insurance_purchased:
            return None
        if dealer_natural:
            ib = self.insurance_bet_amount
            # 取回先前支付的保險額 + 雙倍保險額獎金(2:1 賠率)
            data[userid]["cake"] += ib + 2 * ib
            return f"取回**{ib}**個{self.cake_emoji}保險額，並獲得**{2 * ib}**個{self.cake_emoji}賠償"
        return "保險金沒收"

    @discord.ui.button(label="保險:不可購買",style=discord.ButtonStyle.blurple,row=1)
    async def insurance_button(self,interaction,button: discord.ui.Button):
        userid = str(interaction.user.id)
        error_embed = None
        cake_after = None
        async with common.jsonio_lock:
            data = common.dataload()
            ib = self.insurance_bet_amount
            dealer_ace_up = list(self.bot_cards[0].keys())[0] == "A"
            if self.insurance_purchased or self.player_moved_for_insurance or not dealer_ace_up or self.bet < 2 or ib < 1:
                error_embed = Embed(title="Natalie 21點",description="目前無法購買保險。",color=common.bot_error_color)
            elif data[userid]["cake"] < ib:
                error_embed = Embed(title="Natalie 21點",description=f"{self.cake_emoji}不足，無法購買保險。",color=common.bot_error_color)
            else:
                data[userid]["cake"] -= ib
                self.insurance_purchased = True
                common.datawrite(data)
                cake_after = data[userid]["cake"]
        if error_embed is not None:
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return
        self.configure_insurance_button_state(cake_after)
        message = Embed(title="Natalie 21點",description="",color=common.bot_color)
        sb_desc = self.side_bet_description()
        if sb_desc is not None:
            message.description = sb_desc
        message.add_field(name=f"你的手牌點數:**{BlackJack(self.bot).calculate_point(self.player_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.player_cards)}",inline=False)
        message.add_field(name=f"Natalie的手牌點數:**{self.display_bot_points}**",value=f"{self.display_bot_cards}",inline=False)
        message.set_footer(text=BlackJack(self.bot).win_rate_show(userid, data))
        await interaction.response.edit_message(embed=message,view=self)

    @discord.ui.button(label="拿牌!",style=discord.ButtonStyle.green,row=0)
    async def hit_button(self,interaction,button: discord.ui.Button):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            #關閉雙倍下注
            self.double_button.disabled = True
            self.player_moved_for_insurance = True
            self.configure_insurance_button_state(data[userid]["cake"])
            #加牌
            BlackJack(self.bot).deal_card(self,self.playing_deck,self.player_cards)

            message = Embed(title="Natalie 21點",description="",color=common.bot_color)
            sb_desc = self.side_bet_description()
            if sb_desc is not None:
                message.description = sb_desc
            message.add_field(name=f"你的手牌點數:**{BlackJack(self.bot).calculate_point(self.player_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.player_cards)}",inline=False)
            message.add_field(name=f"Natalie的手牌點數:**{self.display_bot_points}**",value=f"{self.display_bot_cards}",inline=False)
            
            #爆牌
            if BlackJack(self.bot).calculate_point(self.player_cards) > 21:
                if self.insurance_purchased:
                    message.add_field(name=f"Natalie的手牌點數:**{BlackJack(self.bot).calculate_point(self.bot_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.bot_cards)}",inline=False)
                insurance_text = self.resolve_insurance_payout(data, userid, BlackJack(self.bot).dealer_natural_blackjack(self.bot_cards))
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet}**塊{self.cake_emoji}{BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)
                if insurance_text is not None:
                    message.add_field(name="保險", value=insurance_text, inline=False)
                self.hit_button.disabled = True
                self.stand_button.disabled = True
                self.insurance_button.disabled = True
                data[userid]["blackjack_playing"] = False
                data[userid]["blackjack_round"] += 1
                self.stop()
            #過五關
            elif len(self.player_cards) >= 5:
                data[userid]['cake'] += int(self.bet + (self.bet*3))
                data[userid]["blackjack_win_rate"] += 1
                if self.insurance_purchased:
                    message.add_field(name=f"Natalie的手牌點數:**{BlackJack(self.bot).calculate_point(self.bot_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.bot_cards)}",inline=False)
                insurance_text = self.resolve_insurance_payout(data, userid, BlackJack(self.bot).dealer_natural_blackjack(self.bot_cards))
                message.add_field(name="結果",value=f"**過五關!**\n你獲得了**{int(self.bet*3)}**塊{self.cake_emoji}(過五關 x 3.0){BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)
                if insurance_text is not None:
                    message.add_field(name="保險", value=insurance_text, inline=False)
                self.hit_button.disabled = True
                self.stand_button.disabled = True
                self.insurance_button.disabled = True
                data[userid]["blackjack_playing"] = False
                data[userid]["blackjack_round"] += 1
                self.stop()


            common.datawrite(data)
        message.set_footer(text=BlackJack(self.bot).win_rate_show(userid, data))
        await interaction.response.edit_message(embed=message,view=self)

    @discord.ui.button(label="停牌!",style=discord.ButtonStyle.red,row=0)
    async def stand_button(self,interaction,button: discord.ui.Button):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            #關閉所有按鈕
            self.double_button.disabled = True
            self.hit_button.disabled = True
            self.stand_button.disabled = True
            self.insurance_button.disabled = True

            #莊家點數未達17點的話，則加牌直到點數>=17點
            while BlackJack(self.bot).calculate_point(self.bot_cards) < 17:
                BlackJack(self.bot).deal_card(self,self.playing_deck,self.bot_cards)
            
            dealer_natural = BlackJack(self.bot).dealer_natural_blackjack(self.bot_cards)
            message = Embed(title="Natalie 21點",description="",color=common.bot_color)
            sb_desc = self.side_bet_description()
            if sb_desc is not None:
                message.description = sb_desc
            message.add_field(name=f"你的手牌點數:**{BlackJack(self.bot).calculate_point(self.player_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.player_cards)}",inline=False)
            message.add_field(name=f"Natalie的手牌點數:**{BlackJack(self.bot).calculate_point(self.bot_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.bot_cards)}",inline=False) 
            data[userid]["blackjack_round"] += 1

            bot_pts = BlackJack(self.bot).calculate_point(self.bot_cards)
            player_pts = BlackJack(self.bot).calculate_point(self.player_cards)
            #莊家爆牌或者莊家點數比玩家小
            if bot_pts > 21 or (bot_pts < player_pts):
                data[userid]['cake'] += self.bet * 2
                data[userid]["blackjack_win_rate"] += 1
            #莊家的牌比玩家大
            elif (bot_pts > player_pts) and bot_pts <= 21:
                pass
            #平手
            elif (bot_pts == player_pts) and bot_pts <= 21:
                data[userid]['cake'] += self.bet
                data[userid]["blackjack_tie"] += 1

            insurance_text = self.resolve_insurance_payout(data, userid, dealer_natural)

            if bot_pts > 21 or (bot_pts < player_pts):
                message.add_field(name="結果",value=f"你贏了!\n你獲得了**{self.bet}**塊{self.cake_emoji}{BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)
            elif (bot_pts > player_pts) and bot_pts <= 21:
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet}**塊{self.cake_emoji}{BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)
            elif (bot_pts == player_pts) and bot_pts <= 21:
                message.add_field(name="結果",value=f"平手!{BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)

            if insurance_text is not None:
                message.add_field(name="保險", value=insurance_text, inline=False)
            data[userid]["blackjack_playing"] = False
            common.datawrite(data)
        message.set_footer(text=BlackJack(self.bot).win_rate_show(userid, data))
        await interaction.response.edit_message(embed=message,view=self)
        self.stop()

    @discord.ui.button(label="雙倍下注!",style=discord.ButtonStyle.gray,row=0)
    async def double_button(self,interaction,button: discord.ui.Button):
        userid = str(interaction.user.id)
        cake_insufficient = False
        async with common.jsonio_lock:
            data = common.dataload()
            #如果賭注不足以使用雙倍下注
            if data[userid]['cake'] < self.bet:
                self.double_button.disabled = True
                self.double_button.label = "雙倍下注!(蛋糕不足)"
                cake_insufficient = True
            if not cake_insufficient:
                #關閉所有按鈕
                self.double_button.disabled = True
                self.hit_button.disabled = True
                self.stand_button.disabled = True
                self.player_moved_for_insurance = True
                self.configure_insurance_button_state(data[userid]["cake"])

                #雙倍下注要扣的蛋糕
                data[userid]['cake'] -= self.bet
                #加牌
                BlackJack(self.bot).deal_card(self,self.playing_deck,self.player_cards)

                message = Embed(title="Natalie 21點",description="",color=common.bot_color)
                sb_desc = self.side_bet_description()
                if sb_desc is not None:
                    message.description = sb_desc
                message.add_field(name=f"你的手牌點數:**{BlackJack(self.bot).calculate_point(self.player_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.player_cards)}",inline=False)
                data[userid]["blackjack_round"] += 1

                #玩家爆牌
                if BlackJack(self.bot).calculate_point(self.player_cards) > 21:
                    if self.insurance_purchased:
                        message.add_field(name=f"Natalie的手牌點數:**{BlackJack(self.bot).calculate_point(self.bot_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.bot_cards)}",inline=False)
                        insurance_text = self.resolve_insurance_payout(data, userid, BlackJack(self.bot).dealer_natural_blackjack(self.bot_cards))
                    else:
                        insurance_text = None
                        message.add_field(name=f"Natalie的手牌點數:**{self.display_bot_points}**",value=f"{self.display_bot_cards}",inline=False)
                    message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet*2}**塊{self.cake_emoji}{BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)
                    if insurance_text is not None:
                        message.add_field(name="保險", value=insurance_text, inline=False)
                    self.insurance_button.disabled = True
                    data[userid]["blackjack_playing"] = False
                    common.datawrite(data)
                else:
                    #莊家點數未達17點的話，則加牌直到點數>=17點
                    while BlackJack(self.bot).calculate_point(self.bot_cards) < 17:
                        BlackJack(self.bot).deal_card(self,self.playing_deck,self.bot_cards)

                    dealer_natural = BlackJack(self.bot).dealer_natural_blackjack(self.bot_cards)
                    message.add_field(name=f"Natalie的手牌點數:**{BlackJack(self.bot).calculate_point(self.bot_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.bot_cards)}",inline=False)

                    bot_pts = BlackJack(self.bot).calculate_point(self.bot_cards)
                    player_pts = BlackJack(self.bot).calculate_point(self.player_cards)
                    #莊家爆牌或者莊家點數比玩家小
                    if bot_pts > 21 or (bot_pts < player_pts):
                        data[userid]['cake'] += self.bet * 4
                        data[userid]["blackjack_win_rate"] += 1
                    #莊家的牌比玩家大
                    elif (bot_pts > player_pts) and bot_pts <= 21:
                        pass
                    #平手
                    elif (bot_pts == player_pts) and bot_pts <= 21:
                        data[userid]['cake'] += self.bet * 2
                        data[userid]["blackjack_tie"] += 1

                    insurance_text = self.resolve_insurance_payout(data, userid, dealer_natural)

                    if bot_pts > 21 or (bot_pts < player_pts):
                        message.add_field(name="結果",value=f"你贏了!\n你獲得了**{self.bet*2}**塊{self.cake_emoji}{BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)
                    elif (bot_pts > player_pts) and bot_pts <= 21:
                        message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet*2}**塊{self.cake_emoji}{BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)
                    elif (bot_pts == player_pts) and bot_pts <= 21:
                        message.add_field(name="結果",value=f"平手!{BlackJack.side_bet_loss_line(self.side_bet_amount, self.cake_emoji)}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",inline=False)

                    if insurance_text is not None:
                        message.add_field(name="保險", value=insurance_text, inline=False)
                    self.insurance_button.disabled = True
                    data[userid]["blackjack_playing"] = False
                    common.datawrite(data)
        if cake_insufficient:
            await interaction.response.edit_message(view=self)
            return
        message.set_footer(text=BlackJack(self.bot).win_rate_show(userid, data))
        await interaction.response.edit_message(embed=message,view=self)
        self.stop()

    async def interaction_check(self, interaction) -> bool:
        #如果非本人遊玩
        if interaction.user != self.command_interaction.user:
            await interaction.response.send_message(embed=Embed(title="Natalie 21點",description="你不能遊玩別人建立的遊戲。\n(請使用/blackjack遊玩21點)",color=common.bot_error_color), ephemeral=True)
            return False

        return True

    async def on_timeout(self) -> None:
        async with common.jsonio_lock:
            data = common.dataload()

            if data[str(self.command_interaction.user.id)]["blackjack_playing"] == True:
                data[str(self.command_interaction.user.id)]["blackjack_playing"] = False
            common.datawrite(data)


class PokerGame(commands.Cog):
    """Simple poker showdown using seven-card hands."""
    def __init__(self, client: commands.Bot):
        self.bot = client
        self.max_bet = 100000 #最多可下注多少
        self.refund_rate = 0.2 #放棄時，退回本金比例(0.2=20%)
        self.suits = ["<:natalie_clubs:1384128650013704192>", "<:natalie_diamonds:1384126438545821756>", "<:natalie_hearts:1384128667927449600>", "<:natalie_spades:1384128685094993950>"]
        self.ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        self.rank_value = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
        self.rank_order = {
            "高牌": 1,
            "一對": 2,
            "兩對": 3,
            "三條": 4,
            "順子": 5,
            "同花": 6,
            "葫蘆": 7,
            "鐵支": 8,
            "同花順": 9,
            "皇家同花順": 10,
        }

    def create_deck(self):
        deck = [(r, s) for s in self.suits for r in self.ranks]
        random.shuffle(deck)
        return deck

    def evaluate_five_cards(self, cards):
        rank, _ = self.evaluate_five_cards_detailed(cards)
        return rank

    def evaluate_five_cards_detailed(self, cards):
        """
        評估五張牌的詳細牌型和比較值
        
        Args:
            cards: 五張牌的列表，每張牌為 (rank, suit) 元組
                  範例: [("A", "<:natalie_hearts:...>"), ("K", "<:natalie_spades:...>"), ...]
        
        Returns:
            tuple: (牌型名稱, 比較值列表)
                   範例: ("同花順", [14]) 或 ("兩對", [13, 9, 7])
        """
        values = sorted([self.rank_value[r] for r, _ in cards])
        suits = [s for _, s in cards]
        counts = {v: values.count(v) for v in set(values)}
        sorted_counts = sorted(counts.items(), key=lambda x: (-x[1], -x[0]))
        count_values = sorted(counts.values(), reverse=True)
        is_flush = len(set(suits)) == 1
        unique_values = sorted(set(values))
        is_straight = len(unique_values) == 5 and unique_values[-1] - unique_values[0] == 4

        if is_flush and values == [10, 11, 12, 13, 14]:
            return "皇家同花順", [14]
        if is_flush and is_straight:
            return "同花順", [unique_values[-1]]
        if count_values == [4, 1]:
            four = sorted_counts[0][0]
            kicker = [v for v in values if v != four][0]
            return "鐵支", [four, kicker]
        if count_values == [3, 2]:
            triple = sorted_counts[0][0]
            pair = sorted_counts[1][0]
            return "葫蘆", [triple, pair]
        if is_flush:
            return "同花", sorted(values, reverse=True)
        if is_straight:
            return "順子", [unique_values[-1]]
        if count_values == [3, 1, 1]:
            triple = sorted_counts[0][0]
            kickers = sorted([v for v in values if v != triple], reverse=True)
            return "三條", [triple] + kickers
        if count_values == [2, 2, 1]:
            pair1 = sorted_counts[0][0]
            pair2 = sorted_counts[1][0]
            kicker = max([v for v in values if v != pair1 and v != pair2])
            pair_values = sorted([pair1, pair2], reverse=True)
            return "兩對", pair_values + [kicker]
        if count_values == [2, 1, 1, 1]:
            pair = sorted_counts[0][0]
            kickers = sorted([v for v in values if v != pair], reverse=True)
            return "一對", [pair] + kickers
        return "高牌", sorted(values, reverse=True)

    def evaluate_hand(self, cards):
        """
        評估手牌的最佳牌型（僅返回牌型名稱）
        
        Args:
            cards: 手牌列表，每張牌為 (rank, suit) 元組
                  範例: [("A", "<:natalie_hearts:...>"), ("K", "<:natalie_spades:...>"), ...]
                  可以是5張或7張牌
        
        Returns:
            str: 最佳牌型名稱
                 範例: "同花順" 或 "兩對"
        """
        if len(cards) <= 5:
            rank, _ = self.evaluate_five_cards_detailed(cards)
            return rank
        best_rank = "高牌"
        best_order = 0
        best_value = []
        for combo in itertools.combinations(cards, 5):
            rank, value = self.evaluate_five_cards_detailed(list(combo))
            order = self.rank_order[rank]
            if order > best_order or (order == best_order and value > best_value):
                best_order = order
                best_rank = rank
                best_value = value
        return best_rank

    def best_hand_value(self, cards):
        """
        評估手牌的最佳牌型，返回完整信息
        
        Args:
            cards: 手牌列表，每張牌為 (rank, suit) 元組
                  範例: [("A", "<:natalie_hearts:...>"), ("K", "<:natalie_spades:...>"), ...]
                  可以是5張或7張牌
        
        Returns:
            tuple: (牌型名稱, 牌型順序, 比較值列表, 最佳五張牌組合)
                   範例: ("同花順", 9, [14], [("A", "..."), ("K", "..."), ...])
        """
        best_rank = "高牌"
        best_order = 0
        best_value = []
        best_combo = []
        for combo in itertools.combinations(cards, 5):
            rank, value = self.evaluate_five_cards_detailed(list(combo))
            order = self.rank_order[rank]
            if order > best_order or (order == best_order and value > best_value):
                best_rank = rank
                best_order = order
                best_value = value
                best_combo = list(combo)
        return best_rank, best_order, best_value, best_combo

    def extract_rank_cards(self, combo, rank):
        """
        從五張牌組合中提取構成特定牌型的關鍵牌
        
        Args:
            combo: 五張牌的列表，每張牌為 (rank, suit) 元組
                   範例: [("A", "<:natalie_hearts:...>"), ("K", "<:natalie_spades:...>"), ...]
            rank: 牌型名稱
                  範例: "兩對" 或 "三條"
        
        Returns:
            list: 構成該牌型的關鍵牌列表
                  範例: 對於"兩對"可能返回 [("9", "..."), ("9", "..."), ("6", "..."), ("6", "...")]
                  對於"三條"可能返回 [("K", "..."), ("K", "..."), ("K", "...")]
        """
        values = [self.rank_value[r] for r, _ in combo]
        counts = {v: values.count(v) for v in set(values)}

        if rank in ["皇家同花順", "同花順", "順子", "同花", "葫蘆"]:
            return combo
        if rank == "鐵支":
            val = max(v for v, c in counts.items() if c == 4)
            return [card for card in combo if self.rank_value[card[0]] == val]
        if rank == "三條":
            val = max(v for v, c in counts.items() if c == 3)
            return [card for card in combo if self.rank_value[card[0]] == val]
        if rank == "兩對":
            vals = [v for v, c in counts.items() if c == 2]
            return [card for card in combo if self.rank_value[card[0]] in vals]
        if rank == "一對":
            val = max(v for v, c in counts.items() if c == 2)
            return [card for card in combo if self.rank_value[card[0]] == val]
        # 高牌
        high = max(values)
        return [card for card in combo if self.rank_value[card[0]] == high]

    def show_cards(self, cards):
        """
        將牌列表轉換為顯示用的字符串
        
        Args:
            cards: 牌列表，每張牌為 (rank, suit) 元組
                   範例: [("A", "<:natalie_hearts:...>"), ("K", "<:natalie_spades:...>")]
        
        Returns:
            str: 用頓號連接的牌面字符串
                 範例: "A<:natalie_hearts:...>、K<:natalie_spades:...>"
        """
        return "、".join([f"{r}{s}" for r, s in cards])

    def sort_best_cards(self, cards, rank):
        """
        根據牌型對最好牌型進行排序，使顯示更整齊
        
        Args:
            cards: 牌列表，每張牌為 (rank, suit) 元組
                   範例: [("6", "..."), ("6", "..."), ("6", "..."), ("8", "..."), ("8", "...")]
            rank: 牌型名稱
                  範例: "葫蘆" 或 "兩對" 或 "順子"
        
        Returns:
            list: 排序後的牌列表
                  範例: 對於"葫蘆"可能返回 [("6", "..."), ("6", "..."), ("6", "..."), ("8", "..."), ("8", "...")]
                  對於"兩對"可能返回 [("9", "..."), ("9", "..."), ("6", "..."), ("6", "...")]
                  對於"順子"可能返回 [("5", "..."), ("6", "..."), ("7", "..."), ("8", "..."), ("9", "...")]
        """
        if not cards:
            return cards
        
        # 計算每張牌的點數和出現次數
        values = [self.rank_value[r] for r, _ in cards]
        counts = {v: values.count(v) for v in set(values)}
        
        if rank == "順子":
            # 順子：點數從小到大排
            return sorted(cards, key=lambda card: self.rank_value[card[0]])
        elif rank == "葫蘆":
            # 葫蘆：3+2的3排前面，2排後面（如66688）
            triple_val = max(v for v, c in counts.items() if c == 3)
            pair_val = max(v for v, c in counts.items() if c == 2)
            triple_cards = [card for card in cards if self.rank_value[card[0]] == triple_val]
            pair_cards = [card for card in cards if self.rank_value[card[0]] == pair_val]
            return triple_cards + pair_cards
        elif rank == "兩對":
            # 兩對：大的數字排前面（9966）
            pair_vals = sorted([v for v, c in counts.items() if c == 2], reverse=True)
            sorted_cards = []
            for val in pair_vals:
                sorted_cards.extend([card for card in cards if self.rank_value[card[0]] == val])
            return sorted_cards
        elif rank == "皇家同花順" or rank == "同花順":
            # 同花順：點數從小到大排
            return sorted(cards, key=lambda card: self.rank_value[card[0]])
        elif rank == "同花":
            # 同花：點數從大到小排
            return sorted(cards, key=lambda card: self.rank_value[card[0]], reverse=True)
        elif rank == "鐵支":
            # 鐵支：四張相同點數的牌（已經是同一個點數，保持原順序即可）
            return cards
        elif rank == "三條":
            # 三條：三張相同點數的牌（已經是同一個點數，保持原順序即可）
            return cards
        elif rank == "一對":
            # 一對：兩張相同點數的牌（已經是同一個點數，保持原順序即可）
            return cards
        else:  # 高牌
            # 高牌：從大到小排
            return sorted(cards, key=lambda card: self.rank_value[card[0]], reverse=True)

    #顯示勝率跟場數(給embed footer以及leaderboard用的)
    def win_rate_show(self, userid: str) -> str:
        data = common.dataload()
        if "poker_round" not in data[userid]:
            return "你的勝率:未知 總場數:0"
        if data[userid]["poker_round"] == 0:
            return f"你的勝率:未知 總場數:{data[userid]['poker_round']}"
        win_rate = (
            data[userid]["poker_win_rate"] + data[userid]["poker_tie"] * 0.5
        ) / data[userid]["poker_round"]
        return f"你的勝率:{win_rate:.1%} 總場數:{data[userid]['poker_round']}"

    @app_commands.command(name="poker", description="撲克牌比大小")
    @app_commands.describe(bet="要下多少賭注?(支援all、half以及輸入蛋糕數量，最多下注100000)")
    @app_commands.rename(bet="賭注")
    async def poker(self, interaction, bet: str):
        await interaction.response.defer()
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            cake_emoji = self.bot.get_emoji(common.cake_emoji_id)

            if data.get(userid, {}).get("poker_playing"):
                await interaction.followup.send(embed=Embed(title="撲克牌比大小", description="你現在有進行中的遊戲!", color=common.bot_error_color))
                return

            if bet == "all":
                if data[userid]["cake"] >= 1:
                    bet = data[userid]["cake"]
                else:
                    await interaction.followup.send(embed=Embed(title="撲克牌比大小", description=f"你現在沒有任何{cake_emoji}，無法下注!", color=common.bot_error_color))
                    return
            elif bet == "half":
                if data[userid]["cake"] >= 2:
                    bet = data[userid]["cake"] // 2
                else:
                    await interaction.followup.send(embed=Embed(title="撲克牌比大小", description=f"你的{cake_emoji}不足(至少需2個{cake_emoji})，無法下注!", color=common.bot_error_color))
                    return
            elif bet.isdigit() and int(bet) >= 1:
                bet = int(bet)
            else:
                await interaction.followup.send(embed=Embed(title="撲克牌比大小", description=f"無效的數據。(輸入想賭注的{cake_emoji}數量，或者輸入all下注全部的{cake_emoji})", color=common.bot_error_color))
                return

            if data[userid]["cake"] < bet:
                await interaction.followup.send(embed=Embed(title="撲克牌比大小", description=f"{cake_emoji}不足，無法下注!", color=common.bot_error_color))
                return

            if bet > self.max_bet:
                bet = self.max_bet  # 下注最高上限

            data[userid]["cake"] -= bet
            if "poker_tie" not in data[userid]:
                data[userid]["poker_win_rate"] = 0
                data[userid]["poker_round"] = 0
                data[userid]["poker_tie"] = 0
            if "poker_hand_count" not in data[userid]:
                data[userid]["poker_hand_count"] = {
                    rank: 0 for rank in self.rank_order.keys()
                }
            if "poker_raise" not in data[userid]:
                data[userid]["poker_raise"] = 0
            if "poker_fold" not in data[userid]:
                data[userid]["poker_fold"] = 0
            data[userid]["poker_playing"] = True
            common.datawrite(data)

        deck = self.create_deck()
        player_cards = deck[:7]
        bot_cards = deck[7:14]

        player_display = self.show_cards(player_cards[:5]) + "、?、?"
        bot_display = self.show_cards(bot_cards[:4]) + "、?、?、?"

        message = Embed(title="撲克牌比大小", color=common.bot_color)
        message.add_field(name="你的手牌", value=player_display, inline=False)
        message.add_field(name="Natalie的手牌", value=bot_display, inline=False)
        message.set_footer(text=self.win_rate_show(userid))

        await interaction.followup.send(embed=message, view=PokerButton(user=interaction, bet=bet, player_cards=player_cards, bot_cards=bot_cards, client=self.bot))

    @app_commands.command(name="poker_leaderboard", description="撲克牌勝率排行榜")
    async def poker_leaderboard(self, interaction):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            if "poker_tie" not in data.get(userid, {}):
                data[userid]["poker_win_rate"] = 0
                data[userid]["poker_round"] = 0
                data[userid]["poker_tie"] = 0
                common.datawrite(data)

        players = []
        for user_id, user_data in data.items():
            if isinstance(user_data, dict) and "poker_round" in user_data and user_data["poker_round"] >= 50:
                win_rate = (user_data["poker_win_rate"] + user_data["poker_tie"] * 0.5) / user_data["poker_round"]
                players.append({"user_id": user_id, "win_rate": win_rate, "round": user_data["poker_round"]})

        players.sort(key=lambda x: x["win_rate"], reverse=True)
        top_players = players[:5]
        message = ""
        for i, player in enumerate(top_players):
            user_object = self.bot.get_user(int(player["user_id"]))
            message += f"{i+1}.{user_object.display_name} 勝率:**{player['win_rate']:.1%}** 總場數:**{player['round']}**\n"

        if data[userid]["poker_round"] == 0:
            interaction_user_win_rate = 0
        else:
            interaction_user_win_rate = (
                data[userid]["poker_win_rate"] + data[userid]["poker_tie"] * 0.5
            ) / data[userid]["poker_round"]

        await interaction.response.send_message(
            embed=Embed(
                title="撲克牌勝率排行榜",
                description=f"注意:需要遊玩至少50場才會記錄至排行榜。\n{message}\n你的勝率為:**{interaction_user_win_rate:.1%}** 總場數:**{data[userid]['poker_round']}**",
                color=common.bot_color,
            )
        )

    @app_commands.command(name="poker_statistics", description="撲克牌個人統計")
    async def poker_statistics(self, interaction):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            if "poker_hand_count" not in data.get(userid, {}):
                data.setdefault(userid, {})
                data[userid]["poker_hand_count"] = {
                    rank: 0 for rank in self.rank_order.keys()
                }
            if "poker_raise" not in data[userid]:
                data[userid]["poker_raise"] = 0
            if "poker_fold" not in data[userid]:
                data[userid]["poker_fold"] = 0
            if "poker_tie" not in data[userid]:
                data[userid]["poker_win_rate"] = 0
                data[userid]["poker_round"] = 0
                data[userid]["poker_tie"] = 0
            common.datawrite(data)

        order = [
            "皇家同花順",
            "同花順",
            "鐵支",
            "葫蘆",
            "同花",
            "順子",
            "三條",
            "兩對",
            "一對",
            "高牌",
        ]
        hand_lines = "".join(
            f"{r}:{data[userid]['poker_hand_count'].get(r,0)}\n" for r in order
        )
        action_lines = (
            f"加注:{data[userid]['poker_raise']}\n放棄:{data[userid]['poker_fold']}"
        )
        message = Embed(title="撲克牌統計", color=common.bot_color)
        message.add_field(name="牌型出現次數", value=hand_lines, inline=False)
        message.add_field(name="行為次數", value=action_lines, inline=False)
        message.add_field(
            name="勝率&總場數",
            value=self.win_rate_show(userid),
            inline=False,
        )
        await interaction.response.send_message(embed=message)


class PokerButton(discord.ui.View):
    def __init__(self, *, timeout=120, user, bet, player_cards, bot_cards, client):
        super().__init__(timeout=timeout)
        self.command_interaction = user
        self.bet = bet
        self.player_cards = player_cards
        self.bot_cards = bot_cards
        self.bot = client
        self.cake_emoji = self.bot.get_emoji(common.cake_emoji_id)

    def result_message(self, double: bool = False):
        userid = str(self.command_interaction.user.id)
        data = common.dataload()
        (
            player_rank,
            player_order,
            player_value,
            player_combo,
        ) = PokerGame(self.bot).best_hand_value(self.player_cards)
        (
            bot_rank,
            bot_order,
            bot_value,
            bot_combo,
        ) = PokerGame(self.bot).best_hand_value(self.bot_cards)
        pg = PokerGame(self.bot)
        player_best = pg.extract_rank_cards(player_combo, player_rank)
        bot_best = pg.extract_rank_cards(bot_combo, bot_rank)
        if "poker_hand_count" not in data[userid]:
            data[userid]["poker_hand_count"] = {
                rank: 0 for rank in pg.rank_order.keys()
            }
        data[userid]["poker_hand_count"][player_rank] += 1
        message = Embed(title="撲克牌比大小", color=common.bot_color)
        message.add_field(
            name=f"你的手牌(牌型:{player_rank})",
            value=pg.show_cards(self.player_cards)
            + "\n最好牌型:" + pg.show_cards(pg.sort_best_cards(player_best, player_rank)),
            inline=False,
        )
        message.add_field(
            name=f"Natalie的手牌(牌型:{bot_rank})",
            value=pg.show_cards(self.bot_cards)
            + "\n最好牌型:" + pg.show_cards(pg.sort_best_cards(bot_best, bot_rank)),
            inline=False,
        )

        data[userid]["poker_round"] += 1

        # 高牌相同點數時，無需比較其他牌，直接視為平手
        if (
            player_order == bot_order == pg.rank_order["高牌"]
            and player_value[0] == bot_value[0]
        ):
            if double:
                data[userid]["cake"] += self.bet * 2
            else:
                data[userid]["cake"] += self.bet
            data[userid]["poker_tie"] += 1
            message.add_field(
                name="結果",
                value=f"平手!\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",
                inline=False,
            )
        elif player_order > bot_order or (
            player_order == bot_order and player_value > bot_value
        ):
            data[userid]["poker_win_rate"] += 1
            if double:
                data[userid]["cake"] += self.bet * 4
                message.add_field(
                    name="結果",
                    value=f"你贏了!\n你獲得了**{self.bet*2}**塊{self.cake_emoji}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",
                    inline=False,
                )
            else:
                data[userid]["cake"] += self.bet * 2
                message.add_field(
                    name="結果",
                    value=f"你贏了!\n你獲得了**{self.bet}**塊{self.cake_emoji}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",
                    inline=False,
                )
        elif player_order < bot_order or (
            player_order == bot_order and player_value < bot_value
        ):
            lose_amount = self.bet * 2 if double else self.bet
            message.add_field(
                name="結果",
                value=f"你輸了!\n你失去了**{lose_amount}**塊{self.cake_emoji}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",
                inline=False,
            )
        else:
            if double:
                data[userid]["cake"] += self.bet * 2
            else:
                data[userid]["cake"] += self.bet
            data[userid]["poker_tie"] += 1
            message.add_field(
                name="結果",
                value=f"平手!\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",
                inline=False,
            )

        data[userid]["poker_playing"] = False
        common.datawrite(data)
        message.set_footer(text=PokerGame(self.bot).win_rate_show(userid))
        return message

    @discord.ui.button(label="加注!", style=discord.ButtonStyle.gray)
    async def double_button(self, interaction, button: discord.ui.Button):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            if data[userid]["cake"] < self.bet:
                self.double_button.disabled = True
                self.double_button.label = "加注!(蛋糕不足)"
                await interaction.response.edit_message(view=self)
                return
            data[userid]["cake"] -= self.bet
            if "poker_raise" not in data[userid]:
                data[userid]["poker_raise"] = 0
            data[userid]["poker_raise"] += 1
            common.datawrite(data)

        self.double_button.disabled = True
        self.reveal_button.disabled = True
        self.fold_button.disabled = True
        message = self.result_message(double=True)
        await interaction.response.edit_message(embed=message, view=self)
        self.stop()

    @discord.ui.button(label="攤牌!", style=discord.ButtonStyle.green)
    async def reveal_button(self, interaction, button: discord.ui.Button):
        async with common.jsonio_lock:
            message = self.result_message()
            self.double_button.disabled = True
            self.reveal_button.disabled = True
            self.fold_button.disabled = True
            await interaction.response.edit_message(embed=message, view=self)
            self.stop()

    @discord.ui.button(label="放棄...", style=discord.ButtonStyle.red)
    async def fold_button(self, interaction, button: discord.ui.Button):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            refund = int(self.bet * PokerGame(self.bot).refund_rate)
            data[userid]["cake"] += refund
            if "poker_round" in data[userid]:
                data[userid]["poker_round"] += 1
                data[userid]["poker_tie"] += 1
            if "poker_fold" not in data[userid]:
                data[userid]["poker_fold"] = 0
            data[userid]["poker_fold"] += 1
            data[userid]["poker_playing"] = False
            common.datawrite(data)
        self.double_button.disabled = True
        self.reveal_button.disabled = True
        self.fold_button.disabled = True
        message = Embed(title="撲克牌比大小", description=f"你選擇放棄，退回**{refund}**塊{self.cake_emoji}", color=common.bot_color)
        message.set_footer(text=PokerGame(self.bot).win_rate_show(userid))
        await interaction.response.edit_message(embed=message, view=self)
        self.stop()

    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.command_interaction.user:
            await interaction.response.send_message(embed=Embed(title="撲克牌比大小", description="你不能遊玩別人建立的遊戲。", color=common.bot_error_color), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(self.command_interaction.user.id)
            if data.get(userid, {}).get("poker_playing"):
                data[userid]["poker_playing"] = False
                common.datawrite(data)


class SquidRPS(commands.Cog):
    """Squid Game style rock-paper-scissors."""
    def __init__(self, client: commands.Bot):
        self.bot = client
        # 玩家有六種雙手組合，其中重複出的拳只有玩家能選
        # 機器人僅會選擇非重複拳的三種組合
        self.combo_choices = [
            ("✊", "✌️"),
            ("✊", "✋"),
            ("✌️", "✋"),
            ("✊", "✊"),
            ("✌️", "✌️"),
            ("✋", "✋"),
        ]
        self.bot_choices = [
            ("✊", "✋"),
            ("✊", "✌️"),
            ("✌️", "✋"),
        ]

    def _ensure_stats(self, data, userid: str):
        """Ensure squid_rps_stats exists and migrate old keys if needed."""
        user_data = data.setdefault(userid, {"cake": 0})
        if "squid_rps_stats" not in user_data:
            stats = {
                "normal": {
                    "win": user_data.get("squid_rps_win_rate", 0),
                    "round": user_data.get("squid_rps_round", 0),
                },
                "hard": {"win": 0, "round": 0},
            }
            user_data["squid_rps_stats"] = stats
            common.datawrite(data)
        return user_data["squid_rps_stats"]

    def win_rate_show(self, userid: str, difficulty: str | None = None) -> str:
        data = common.dataload()
        stats = self._ensure_stats(data, userid)
        if difficulty is None:
            difficulty = data.get(userid, {}).get("squid_rps_difficulty", "normal")
        win = stats[difficulty]["win"]
        round_count = stats[difficulty]["round"]
        if round_count == 0:
            return f"你的勝率:未知 總場數:{round_count}"
        win_rate = win / round_count
        return f"你的勝率:{win_rate:.1%} 總場數:{round_count}"

    def rps_result(self, a: str, b: str) -> int:
        if a == b:
            return 0
        win_table = {("✊", "✌️"), ("✌️", "✋"), ("✋", "✊")}
        if (a, b) in win_table:
            return 1
        return -1

    @app_commands.command(name="squid_rps", description="魷魚遊戲的猜拳")
    @app_commands.describe(bet="要下多少賭注?(支援all、half以及輸入蛋糕數量)")
    @app_commands.rename(bet="賭注")
    async def squid_rps(self, interaction, bet: str):
        await interaction.response.defer()
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            cake_emoji = self.bot.get_emoji(common.cake_emoji_id)

            if data.get(userid, {}).get("squid_playing"):
                await interaction.followup.send(
                    embed=Embed(
                        title="魷魚猜拳",
                        description="你現在有進行中的遊戲!",
                        color=common.bot_error_color,
                    )
                )
                return

            if bet == "all":
                if data[userid]["cake"] >= 1:
                    bet = data[userid]["cake"]
                else:
                    await interaction.followup.send(
                        embed=Embed(
                            title="魷魚猜拳",
                            description=f"你現在沒有任何{cake_emoji}，無法下注!",
                            color=common.bot_error_color,
                        )
                    )
                    return
            elif bet == "half":
                if data[userid]["cake"] >= 2:
                    bet = data[userid]["cake"] // 2
                else:
                    await interaction.followup.send(
                        embed=Embed(
                            title="魷魚猜拳",
                            description=f"你的{cake_emoji}不足(至少需2個{cake_emoji})，無法下注!",
                            color=common.bot_error_color,
                        )
                    )
                    return
            elif bet.isdigit() and int(bet) >= 1:
                bet = int(bet)
            else:
                await interaction.followup.send(
                    embed=Embed(
                        title="魷魚猜拳",
                        description=f"無效的數據。(輸入想賭注的{cake_emoji}數量，或者輸入all下注全部的{cake_emoji})",
                        color=common.bot_error_color,
                    )
                )
                return

            if data[userid]["cake"] < bet:
                await interaction.followup.send(
                    embed=Embed(
                        title="魷魚猜拳",
                        description=f"{cake_emoji}不足，無法下注!",
                        color=common.bot_error_color,
                    )
                )
                return

            data[userid]["cake"] -= bet
            stats = self._ensure_stats(data, userid)
            if "squid_rps_difficulty" not in data[userid]:
                data[userid]["squid_rps_difficulty"] = "normal"
            difficulty = data[userid]["squid_rps_difficulty"]
            data[userid]["squid_playing"] = True
            common.datawrite(data)

        view = SquidRPSView(user=interaction, bet=bet, client=self.bot, difficulty=difficulty)
        message = Embed(
            title="魷魚猜拳",
            description="請選擇你要出的雙手組合",
            color=common.bot_color,
        )
        message.add_field(name="難度", value=difficulty, inline=False)
        if difficulty == "hard":
            message.add_field(name="Natalie血量", value=view.hp_display(), inline=False)
        message.add_field(name="手槍彈夾", value=view.clip_display(), inline=False)
        message.set_footer(text=self.win_rate_show(userid))
        msg = await interaction.followup.send(embed=message, view=view)
        view.message = msg

    @app_commands.command(name="squid_rps_setdifficulty", description="設定魷魚猜拳難度")
    @app_commands.describe(level="選擇難度")
    @app_commands.rename(level="難度")
    @app_commands.choices(level=[
        app_commands.Choice(name="normal (Natalie一條命)", value="normal"),
        app_commands.Choice(name="hard (Natalie有兩條命，獲勝蛋糕x3)", value="hard"),
    ])
    async def squid_rps_setdifficulty(self, interaction, level: app_commands.Choice[str]):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            if userid not in data:
                data[userid] = {"cake": 0}
            self._ensure_stats(data, userid)
            data[userid]["squid_rps_difficulty"] = level.value
            common.datawrite(data)
        await interaction.response.send_message(embed=Embed(title="魷魚猜拳難度設置", description=f"已設定為{level.value}", color=common.bot_color))

    @app_commands.command(name="squid_rps_leaderboard", description="魷魚猜拳勝率排行榜")
    async def squid_rps_leaderboard(self, interaction):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            stats = self._ensure_stats(data, userid)

        leaderboards = {"normal": [], "hard": []}
        for user_id, user_data in data.items():
            if not isinstance(user_data, dict):
                continue
            user_stats = self._ensure_stats(data, user_id)
            for diff in ("normal", "hard"):
                if user_stats[diff]["round"] >= 50:
                    win_rate = user_stats[diff]["win"] / user_stats[diff]["round"]
                    leaderboards[diff].append({
                        "user_id": user_id,
                        "win_rate": win_rate,
                        "round": user_stats[diff]["round"],
                    })

        for diff in leaderboards:
            leaderboards[diff].sort(key=lambda x: x["win_rate"], reverse=True)

        def fmt_board(players):
            msg = ""
            for i, player in enumerate(players[:5]):
                user_obj = self.bot.get_user(int(player["user_id"]))
                msg += f"{i+1}.{user_obj.display_name} 勝率:**{player['win_rate']:.1%}** 總場數:**{player['round']}**\n"
            return msg or "無資料\n"

        msg_normal = fmt_board(leaderboards["normal"])
        msg_hard = fmt_board(leaderboards["hard"])

        normal_rate = stats["normal"]["win"] / stats["normal"]["round"] if stats["normal"]["round"] else 0
        hard_rate = stats["hard"]["win"] / stats["hard"]["round"] if stats["hard"]["round"] else 0

        desc = (
            "注意:需要遊玩至少50場才會記錄至排行榜。\n"
            f"\n**Normal**\n{msg_normal}"
            f"\n**Hard**\n{msg_hard}"
            f"\n你在normal難度下勝率為:{normal_rate:.1%} 總場數:{stats['normal']['round']}"
            f"\n你在hard難度下勝率為:{hard_rate:.1%} 總場數:{stats['hard']['round']}"
        )

        await interaction.response.send_message(
            embed=Embed(title="魷魚猜拳勝率排行榜", description=desc, color=common.bot_color)
        )


class SquidRPSStrategy:
    """猜拳策略"""

    def __init__(self, *, case3_prob: float = 2/3, case4_prob: float = 3/4):
        # 機率設定:case3為輸&平手、贏&輸情形留左手的機率
        self.case3_prob = case3_prob
        # 機率設定:case4為贏&輸、平手&贏情形留右手的機率
        self.case4_prob = case4_prob

    @staticmethod
    def rps_result(a: str, b: str) -> int:
        """Return 1 if a beats b, 0 if tie, -1 if lose."""
        if a == b:
            return 0
        win_table = {("✊", "✌️"), ("✌️", "✋"), ("✋", "✊")}
        return 1 if (a, b) in win_table else -1

    def decide(self, bot_combo, player_combo) -> int:
        """Decide which hand to keep. Return 0 for first, 1 for second."""
        r0 = (
            self.rps_result(bot_combo[0], player_combo[0]),
            self.rps_result(bot_combo[0], player_combo[1]),
        )
        r1 = (
            self.rps_result(bot_combo[1], player_combo[0]),
            self.rps_result(bot_combo[1], player_combo[1]),
        )

        result_set = {r0, r1}

        def index_of(target) -> int:
            """Return the index of the target result tuple."""
            return 0 if r0 == target else 1

        # 平手&輸、贏&平手 -> 留下贏&平手或平手&贏的手
        if result_set == {(0, -1), (1, 0)}:
            return index_of((1, 0))
        if result_set == {(0, 1), (-1, 0)}:
            return index_of((0, 1))

        # 平手&平手、贏&贏 -> 留下贏&贏的手
        if result_set == {(0, 0), (1, 1)}:
            return index_of((1, 1))

        # 輸&平手、贏&輸 -> 2/3機率留下輸&平手的手
        if result_set == {(-1, 0), (1, -1)}:
            return index_of((-1, 0)) if random.random() < self.case3_prob else index_of((1, -1))

        # 贏&輸、平手&贏 -> 3/4機率留下平手&贏的手
        if result_set == {(1, -1), (0, 1)}:
            return index_of((0, 1)) if random.random() < self.case4_prob else index_of((1, -1))

        # 平手&平手、平手&輸 -> 留下平手&平手的手
        if result_set == {(0, 0), (0, -1)}:
            return index_of((0, 0))

        # 贏&贏、輸&輸 -> 留下贏&贏的手
        if result_set == {(1, 1), (-1, -1)}:
            return index_of((1, 1))

        # 平手&平手、輸&輸 -> 留下平手&平手的手
        if result_set == {(0, 0), (-1, -1)}:
            return index_of((0, 0))

        # 其他情形隨機
        return random.randint(0, 1)


class SquidRPSView(discord.ui.View):
    def __init__(self, *, timeout=120, user, bet, client, difficulty="normal"):
        super().__init__(timeout=timeout)
        self.command_interaction = user
        self.bet = bet
        self.bot = client
        # 建立猜拳策略
        self.strategy = SquidRPSStrategy()
        self.cake_emoji = self.bot.get_emoji(common.cake_emoji_id)
        self.difficulty = difficulty
        self.natalie_hp = 2 if difficulty == "hard" else 1
        self.max_hp = self.natalie_hp
        if difficulty == "hard":
            self.bullet_positions = set(random.sample(range(6), 2))
        else:
            self.bullet_positions = {random.randint(0, 5)}
        self.message = None
        self.player_combo = None
        self.bot_combo = None
        self.bot_keep = None
        self.keep_task = None
        # 確保每回合只處理一次收拳結果
        self.hand_selected = False
        # 追蹤已扣下的扳機次數
        self.shots_fired = 0

    def hp_display(self) -> str:
        """顯示Natalie目前血量"""
        lost = self.max_hp - self.natalie_hp
        return "".join("○" if i < lost else "●" for i in range(self.max_hp))

    async def _edit_message(self, interaction, *, embed, view):
        if interaction is not None:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await self.message.edit(embed=embed, view=view)

    def clip_display(self) -> str:
        """顯示目前彈夾狀態"""
        return "".join("○" if i < self.shots_fired else "●" for i in range(6))

    async def reset_round(self):
        for b in self.combo_buttons:
            b.disabled = False
        self.left_button.disabled = True
        self.right_button.disabled = True
        if self.keep_task:
            self.keep_task.cancel()
            self.keep_task = None
        self.player_combo = None
        self.bot_combo = None
        self.bot_keep = None
        self.hand_selected = False
        embed = Embed(
            title="魷魚猜拳",
            description="請選擇你要出的雙手組合",
            color=common.bot_color,
        )
        embed.add_field(name="難度", value=self.difficulty, inline=False)
        if self.difficulty == "hard":
            embed.add_field(name="Natalie血量", value=self.hp_display(), inline=False)
        embed.add_field(name="手槍彈夾", value=self.clip_display(), inline=False)
        embed.set_footer(
            text=SquidRPS(self.bot).win_rate_show(
                str(self.command_interaction.user.id), self.difficulty
            )
        )
        await self.message.edit(embed=embed, view=self)

    def compare(self, p, b):
        return SquidRPS(self.bot).rps_result(p, b)

    async def choose_combo(self, interaction, combo):
        self.player_combo = combo
        self.bot_combo = random.choice(SquidRPS(self.bot).bot_choices)
        # 使用策略決定收哪一隻手
        self.bot_keep = self.strategy.decide(self.bot_combo, combo)
        for b in self.combo_buttons:
            b.disabled = True
        self.left_button.disabled = False
        self.right_button.disabled = False
        embed = Embed(
            title="魷魚猜拳",
            description="選擇要收掉哪隻手",
            color=common.bot_color,
        )
        embed.add_field(name="難度", value=self.difficulty, inline=False)
        if self.difficulty == "hard":
            embed.add_field(name="Natalie血量", value=self.hp_display(), inline=False)
        embed.add_field(name="Natalie的雙手", value=f"{self.bot_combo[0]}、{self.bot_combo[1]}", inline=False)
        embed.add_field(name="你的雙手", value=f"{combo[0]}、{combo[1]}", inline=False)
        embed.add_field(name="手槍彈夾", value=self.clip_display(), inline=False)

        embed.add_field(name="思考時間", value="5秒", inline=False)
        await self._edit_message(interaction, embed=embed, view=self)
        if self.keep_task:
            self.keep_task.cancel()
        self.keep_task = asyncio.create_task(self._keep_timer())

    async def _keep_timer(self):
        await asyncio.sleep(5)
        if self.keep_task:
            self.keep_task = None
            index = random.randint(0, 1)
            await self.keep_hand(None, index)


    @discord.ui.button(label="✊&✌️", style=discord.ButtonStyle.gray)
    async def combo1(self, interaction, button):
        await self.choose_combo(interaction, ("✊", "✌️"))

    @discord.ui.button(label="✊&✋", style=discord.ButtonStyle.gray)
    async def combo2(self, interaction, button):
        await self.choose_combo(interaction, ("✊", "✋"))

    @discord.ui.button(label="✌️&✋", style=discord.ButtonStyle.gray)
    async def combo3(self, interaction, button):
        await self.choose_combo(interaction, ("✌️", "✋"))

    @discord.ui.button(label="✊✊", style=discord.ButtonStyle.gray)
    async def combo4(self, interaction, button):
        await self.choose_combo(interaction, ("✊", "✊"))

    @discord.ui.button(label="✌️✌️", style=discord.ButtonStyle.gray)
    async def combo5(self, interaction, button):
        await self.choose_combo(interaction, ("✌️", "✌️"))

    @discord.ui.button(label="✋✋", style=discord.ButtonStyle.gray)
    async def combo6(self, interaction, button):
        await self.choose_combo(interaction, ("✋", "✋"))

    @discord.ui.button(label="收左手", style=discord.ButtonStyle.blurple, disabled=True)
    async def left_button(self, interaction, button):
        await self.keep_hand(interaction, 1)

    @discord.ui.button(label="收右手", style=discord.ButtonStyle.blurple, disabled=True)
    async def right_button(self, interaction, button):
        await self.keep_hand(interaction, 0)

    @property
    def combo_buttons(self):
        return [self.combo1, self.combo2, self.combo3, self.combo4, self.combo5, self.combo6]

    async def keep_hand(self, interaction, index):
        if self.hand_selected:
            if interaction is not None:
                await interaction.response.send_message(
                    embed=Embed(
                        title="魷魚猜拳",
                        description="這回合已經收拳了!",
                        color=common.bot_error_color,
                    ),
                    ephemeral=True,
                )
            return
        self.hand_selected = True
        if self.keep_task:
            self.keep_task.cancel()
            self.keep_task = None
        self.left_button.disabled = True
        self.right_button.disabled = True
        player_choice = self.player_combo[index]
        bot_choice = self.bot_combo[self.bot_keep]
        result = self.compare(player_choice, bot_choice)
        desc = f"你出{player_choice}，Natalie出{bot_choice}"

        if result == 0:
            desc += "，平手!"
            embed = Embed(title="魷魚猜拳", description=desc, color=common.bot_color)
            embed.add_field(name="難度", value=self.difficulty, inline=False)
            if self.difficulty == "hard":
                embed.add_field(name="Natalie血量", value=self.hp_display(), inline=False)
            embed.add_field(name="手槍彈夾", value=self.clip_display(), inline=False)
            embed.set_footer(
                text=SquidRPS(self.bot).win_rate_show(
                    str(self.command_interaction.user.id), self.difficulty
                )
            )
            await self._edit_message(interaction, embed=embed, view=self)

            await asyncio.sleep(3.5) #等3.5秒讓玩家確認結果
            await self.reset_round()
            return

        # 扣下扳機
        self.shots_fired += 1
        shot_index = self.shots_fired - 1
        shot = shot_index in self.bullet_positions
        if shot:
            self.bullet_positions.discard(shot_index)
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(self.command_interaction.user.id)
            if result == 1:
                desc += "，你贏了!"
                if shot:
                    self.natalie_hp -= 1
                    if self.natalie_hp == 0:
                        desc += "\n砰! 實彈擊中Natalie，你贏得了遊戲!"
                        reward = self.bet * (4 if self.difficulty == "hard" else 2)
                        gain = reward - self.bet
                        data[userid]["cake"] += reward
                        data[userid]["squid_playing"] = False
                        stats = SquidRPS(self.bot)._ensure_stats(data, userid)
                        stats[self.difficulty]["win"] += 1
                        stats[self.difficulty]["round"] += 1
                        embed = Embed(title="魷魚猜拳", description=desc, color=common.bot_color)
                        embed.add_field(name="難度", value=self.difficulty, inline=False)
                        if self.difficulty == "hard":
                            embed.add_field(name="Natalie血量", value=self.hp_display(), inline=False)
                        embed.add_field(name="手槍彈夾", value=self.clip_display(), inline=False)
                        if self.difficulty == "normal":
                            result_message = f"你獲得了**{gain}**塊{self.cake_emoji}\n"
                        elif self.difficulty == "hard":
                            result_message = f"你獲得了**{gain}**塊{self.cake_emoji} (hard * 3)\n"
                        result_message += f"你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}"
                        embed.add_field(
                            name="結果",
                            value=result_message,
                            inline=False,
                        )
                        common.datawrite(data)

                        embed.set_footer(
                            text=SquidRPS(self.bot).win_rate_show(userid, self.difficulty)
                        )
                        await self._edit_message(interaction, embed=embed, view=None)

                        self.stop()
                        return
                    else:
                        desc += "\n砰! Natalie受傷了..."
                        embed = Embed(title="魷魚猜拳", description=desc, color=common.bot_color)
                        embed.add_field(name="難度", value=self.difficulty, inline=False)
                        embed.add_field(name="Natalie血量", value=self.hp_display(), inline=False)
                        embed.add_field(name="手槍彈夾", value=self.clip_display(), inline=False)
                        common.datawrite(data)

                        embed.set_footer(
                            text=SquidRPS(self.bot).win_rate_show(userid, self.difficulty)
                        )
                        await self._edit_message(interaction, embed=embed, view=self)

                        await asyncio.sleep(3.5)
                        await self.reset_round()
                        return
                else:
                    desc += "\n是空包彈... 下一回合!"
                    embed = Embed(title="魷魚猜拳", description=desc, color=common.bot_color)
                    embed.add_field(name="難度", value=self.difficulty, inline=False)
                    if self.difficulty == "hard":
                        embed.add_field(name="Natalie血量", value=self.hp_display(), inline=False)
                    embed.add_field(name="手槍彈夾", value=self.clip_display(), inline=False)
                    common.datawrite(data)

                    embed.set_footer(
                        text=SquidRPS(self.bot).win_rate_show(userid, self.difficulty)
                    )
                    await self._edit_message(interaction, embed=embed, view=self)

                    await asyncio.sleep(3.5)  # 等3.5秒讓玩家確認結果
                    await self.reset_round()
                    return
            else:
                desc += "，你輸了..."
                if shot:
                    desc += "\n砰! 你被實彈擊中了..."
                    data[userid]["squid_playing"] = False
                    stats = SquidRPS(self.bot)._ensure_stats(data, userid)
                    stats[self.difficulty]["round"] += 1
                    embed = Embed(title="魷魚猜拳", description=desc, color=common.bot_color)
                    embed.add_field(name="難度", value=self.difficulty, inline=False)
                    if self.difficulty == "hard":
                        embed.add_field(name="Natalie血量", value=self.hp_display(), inline=False)
                    embed.add_field(name="手槍彈夾", value=self.clip_display(), inline=False)
                    embed.add_field(
                        name="結果",
                        value=f"你失去了**{self.bet}**塊{self.cake_emoji}\n你現在擁有**{data[userid]['cake']}**塊{self.cake_emoji}",
                        inline=False,
                    )
                    common.datawrite(data)

                    embed.set_footer(
                        text=SquidRPS(self.bot).win_rate_show(userid, self.difficulty)
                    )
                    await self._edit_message(interaction, embed=embed, view=None)
                    self.stop()
                    return
                else:
                    desc += "\n是空包彈... 下一回合!"
                    embed = Embed(title="魷魚猜拳", description=desc, color=common.bot_color)
                    embed.add_field(name="難度", value=self.difficulty, inline=False)
                    if self.difficulty == "hard":
                        embed.add_field(name="Natalie血量", value=self.hp_display(), inline=False)
                    embed.add_field(name="手槍彈夾", value=self.clip_display(), inline=False)
                    common.datawrite(data)

                    embed.set_footer(
                        text=SquidRPS(self.bot).win_rate_show(userid, self.difficulty)
                    )
                    await self._edit_message(interaction, embed=embed, view=self)

                    await asyncio.sleep(3.5)  # 等3.5秒讓玩家確認結果
                    await self.reset_round()
                    return

    async def interaction_check(self, interaction) -> bool:
        if interaction.user != self.command_interaction.user:
            await interaction.response.send_message(
                embed=Embed(title="魷魚猜拳", description="你不能遊玩別人建立的遊戲。", color=common.bot_error_color),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(self.command_interaction.user.id)
            if data.get(userid, {}).get("squid_playing"):
                data[userid]["squid_playing"] = False
                common.datawrite(data)



        


class CollectionTradeButton(discord.ui.View):
    def __init__(self, *,timeout= 60,selluser,collection_name,price,client):
        super().__init__(timeout=timeout)
        self.bot = client
        self.selluser = selluser
        self.collection_name = collection_name
        self.price = price

    @discord.ui.button(label="購買!",style=discord.ButtonStyle.green)
    async def collection_trade_button(self,interaction,button: discord.ui.Button):
        async with common.jsonio_lock:
            user_data = common.dataload()
            selluserid = str(self.selluser.user.id)
            buyuserid = str(interaction.user.id)
            mining_data = MiningGame(self.bot).miningdata_read(buyuserid)

            #買家有沒有錢?
            if user_data[buyuserid]["cake"] < self.price:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"錯誤:你只有**{user_data[buyuserid]['cake']}**塊蛋糕。",color=common.bot_error_color),ephemeral=True)
                return

            button.disabled = True
            user_data[selluserid]["cake"] += self.price
            user_data[buyuserid]["cake"] -= self.price
            mining_data[selluserid]["collections"][self.collection_name] -= 1
            if self.collection_name not in mining_data[buyuserid]["collections"]:
                mining_data[buyuserid]["collections"][self.collection_name] = 0
            mining_data[buyuserid]["collections"][self.collection_name] += 1

            common.datawrite(user_data)
            common.datawrite(mining_data,"data/mining.json")

            await interaction.response.edit_message(embed=Embed(title="Natalie 挖礦",description=f"此筆交易提案已完成。\n賣家:<@{selluserid}>\n買家:<@{buyuserid}>\n購買項目:**{self.collection_name}**",color=common.bot_color),view=self)
    
    async def interaction_check(self, interaction) -> bool:
        if interaction.user == self.selluser.user:
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你不能向自己購買收藏品。",color=common.bot_error_color), ephemeral=True)
            return False
        return True

class AutofixButton(discord.ui.View):
    def __init__(self, *,timeout= 30):
        super().__init__(timeout=timeout)
    
    @discord.ui.button(label="關閉自動修理",style=discord.ButtonStyle.danger)
    async def autofix_button(self,interaction,button: discord.ui.Button):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            data = common.dataload("data/mining.json")
            data[userid]["autofix"] = False
            common.datawrite(data,"data/mining.json")
            button.disabled = True
            await interaction.response.edit_message(embed=Embed(title="Natalie 挖礦",description="自動修理已關閉。",color=common.bot_color),view=self)

async def setup(client:commands.Bot):
    await client.add_cog(MiningGame(client))
    await client.add_cog(BlackJack(client))
    await client.add_cog(PokerGame(client))
    await client.add_cog(SquidRPS(client))
