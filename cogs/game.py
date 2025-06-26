import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
import random
import itertools
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
        "森林礦坑": {"石頭": 0.3, "鐵礦": 0.45, "金礦": 0.25, "鈦晶": 0, "鑽石": 0},
        "荒野高原": {"石頭": 0.1, "鐵礦": 0.45, "金礦": 0.25, "鈦晶": 0.2, "鑽石": 0},
        "蛋糕仙境": {"石頭": 0, "鐵礦": 0.38, "金礦": 0.32, "鈦晶": 0.25, "鑽石": 0.05},
        "永世凍土": {"石頭": 0, "鐵礦": 0.25, "金礦": 0.36, "鈦晶": 0.27, "鑽石": 0.12},
        "熾熱火炎山": {"石頭": 0, "鐵礦": 0, "金礦": 0.43, "鈦晶": 0.35, "鑽石": 0.22},
        "虛空洞穴": {"石頭": 0, "鐵礦": 0, "金礦": 0.3, "鈦晶": 0.4, "鑽石": 0.3}
        }
        self.mine_levellimit = {
            "森林礦坑": 1,
            "荒野高原": 10,
            "蛋糕仙境": 18,
            "永世凍土": 26,
            "熾熱火炎山": 34,
            "虛空洞穴": 42
        }
        self.collection_list = {
        "森林礦坑": ["昆蟲化石", "遠古的妖精翅膀", "萬年神木之根", "古代陶器碎片"],
        "荒野高原": ["風的根源石", "儀式石碑", "被詛咒的匕首", "神祕骷髏項鍊"],
        "蛋糕仙境": ["不滅的蠟燭", "蛋糕製造機", "異界之門鑰匙"],
        "永世凍土": ["雪怪排泄物", "冰鎮草莓甜酒", "冰凍章魚觸手"],
        "熾熱火炎山": ["上古琥珀", "火龍遺骨", "地獄辣炒年糕"],
        "虛空洞穴": ["反物質研究手稿", "異星生物黏液", "深淵的彼岸花"]
        }
        self.mineral_pricelist = {
            "鐵礦": 5,
            "金礦": 10,
            "鈦晶": 20,
            "鑽石": 50
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

        return data


    @app_commands.command(name = "mining", description = "挖礦!")
    @app_commands.checks.cooldown(1, 8)
    async def mining(self,interaction):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            user_data = common.dataload()
            mining_data = self.miningdata_read(userid)
            userlevel = common.LevelSystem().read_info(userid)

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
                else:
                    await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的礦鎬已經壞了!",color=common.bot_error_color))
                    return


            mining_data['mine_mininglimit'][mining_data[userid]['mine']] -= 1
            mining_data[userid]["pickaxe_health"] -=10
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="正在挖礦中...",color=common.bot_color))
            #寫入檔案防止回溯
            common.datawrite(user_data)
            common.datawrite(mining_data,"data/mining.json")

        #挖礦時間8秒
        await asyncio.sleep(8)

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
                    #抽出礦物
                    message = Embed(title="Natalie 挖礦",description=f"你挖到了**{reward}**!",color=common.bot_color)
                    if reward != "石頭":
                        if reward not in mining_data[userid]:
                            mining_data[userid][reward] = 0
                        mining_data[userid][reward] += 1

                        # bonus minerals
                        if mining_data[userid]['pickaxe'] == "鑽石鎬":
                            bonus_probability = 0.1
                            bonus_mineral = 1
                        elif mining_data[userid]['pickaxe'] == "不要鎬":
                            bonus_probability = 0.15
                            bonus_mineral = 1
                        else:
                            bonus_probability = 0
                            bonus_mineral = 0

                        if random.random() < bonus_probability:
                            mining_data[userid][reward] += bonus_mineral
                            message.description += f"\n你額外獲得了**{bonus_mineral}**個**{reward}**!"
                    break

            #開始抽收藏品(0.5%機會)
            random_num = random.random()
            if random_num < 0.005:
                collection = random.choice(self.collection_list[mining_data[userid]["mine"]])
                if collection not in mining_data[userid]["collections"]:
                    mining_data[userid]["collections"][collection] = 0
                mining_data[userid]["collections"][collection] += 1
                message.add_field(name="找到收藏品!",value=f"獲得**{collection}**!",inline= False)

            #高風險礦場機率爆裝
            random_num = random.random()
            if random_num < 0.05 and (mining_data[userid]["mine"] == "熾熱火炎山" or mining_data[userid]["mine"] == "虛空洞穴"):
                mining_data[userid]["pickaxe_health"] = 0
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

        message = Embed(title="Natalie 挖礦",description="指令:\n/mining 挖礦\n/pickaxe_fix 修理礦鎬\n/pickaxe_autofix 自動修理礦鎬\n/mineral_sell 賣出礦物\n/collection_trade 收藏品交易\n/collection_sell 販賣收藏品給Natalie\n/mine 更換礦場\n/pickaxe_buy 購買礦鎬\n/redeem_collection_role 兌換收藏品稱號\n(注意:本指令缺乏測試，兌換前建議\n先使用mining_info留下收藏品資料。)\n/mining_machine_info 關於自動挖礦機",color=common.bot_color)
        message.add_field(name="我的礦鎬",value=f"{mining_data[userid]['pickaxe']}  {mining_data[userid]['pickaxe_health']}/{mining_data[userid]['pickaxe_maxhealth']}",inline=False)
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
        app_commands.Choice(name="熾熱火炎山  34等", value="熾熱火炎山"),
        app_commands.Choice(name="虛空洞穴  42等", value="虛空洞穴")
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
        app_commands.Choice(name="不要鎬  耐久:1000 需要25等 $5000", value="不要鎬")
        ])
    async def pickaxe_buy(self,interaction,choices: app_commands.Choice[str]):
        async with common.jsonio_lock:
            userid = str(interaction.user.id)
            user_data = common.dataload()
            mining_data = self.miningdata_read(userid)
        
            if mining_data[userid]["pickaxe"] == choices.value:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你已經擁有此礦鎬了!",color=common.bot_error_color))
                return
            if self.pickaxe_list[choices.value]['需求等級'] > user_data[userid]['level']:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的等級不足以購買此礦鎬!",color=common.bot_error_color))
                return
            if self.pickaxe_list[choices.value]['需求等級'] < self.pickaxe_list[mining_data[userid]['pickaxe']]['需求等級']:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你不能購買更劣質的礦鎬!",color=common.bot_error_color))
                return
            if user_data[userid]['cake'] < self.pickaxe_list[choices.value]['價格']:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"你沒有足夠的蛋糕購買此礦鎬!(購買需要**{self.pickaxe_list[choices.value]['價格']}**，你只有**{user_data[userid]['cake']}**)。",color=common.bot_error_color))
                return

            # 允許購買
            user_data[userid]['cake'] -= self.pickaxe_list[choices.value]['價格']
            mining_data[userid]["pickaxe"] = choices.value
            mining_data[userid]['pickaxe_maxhealth'] = self.pickaxe_list[choices.value]['耐久度']
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"購買成功! 你現在擁有了**{choices.value}**。",color=common.bot_color))
            common.datawrite(user_data)
            common.datawrite(mining_data,"data/mining.json")
        
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
        app_commands.Choice(name="熾熱火炎山  34等", value="熾熱火炎山"),
        app_commands.Choice(name="虛空洞穴  42等", value="虛空洞穴")
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

    #顯示牌面
    def show_cards(self,player_cards):
        return '、'.join([list(card.keys())[0] for card in player_cards])

    #顯示勝率跟場數(給embed footer以及leaderboard用的)
    def win_rate_show(self,userid:str) ->str:
        data = common.dataload()
        if data[userid]["blackjack_round"] == 0:
            return f"你的勝率:未知 總場數:{data[userid]['blackjack_round']}"
        else:
            win_rate = (data[userid]['blackjack_win_rate'] + data[userid]['blackjack_tie'] * 0.5)/data[userid]['blackjack_round']
            return f"你的勝率:{win_rate:.1%} 總場數:{data[userid]['blackjack_round']}"



    @app_commands.command(name = "blackjack", description = "21點!")
    @app_commands.describe(bet="要下多少賭注?(支援all、half以及輸入蛋糕數量)")
    @app_commands.rename(bet="賭注")
    async def blackjack(self,interaction,bet: str):
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
            #下全部
            if bet == "all":
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

            #檢查蛋糕是否足夠
            if data[userid]['cake'] < bet:
                await interaction.followup.send(embed=Embed(title="Natalie 21點",description=f"{cake_emoji}不足，無法下注!",color=common.bot_error_color))
                return
            data[userid]['cake'] -= bet

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
            #玩家如果是blackjack(持有兩張牌且點數剛好為21)
            if self.calculate_point(player_cards) == 21:
                data[userid]['cake'] += int(bet + (bet*1.5))
                message.add_field(name="結果",value=f"**BlackJack!**\n你獲得了**{int(bet*1.5)}**塊{cake_emoji}(blackjack! x 1.5)\n你現在有**{data[userid]['cake']}**塊{cake_emoji}",inline=False)
                data[userid]["blackjack_win_rate"] += 1
                data[userid]["blackjack_round"] += 1
                common.datawrite(data)
                message.set_footer(text=self.win_rate_show(userid))
                await interaction.followup.send(embed=message)
                return
            
            data[userid]["blackjack_playing"] = True
            common.datawrite(data)
        #選項給予
        message.set_footer(text=self.win_rate_show(userid))
        await interaction.followup.send(embed=message,view = BlackJackButton(user=interaction,bet=bet,player_cards=player_cards,bot_cards=bot_cards,playing_deck=playing_deck,client=self.bot,display_bot_points=display_bot_points,display_bot_cards=display_bot_cards))


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
    def __init__(self, *,timeout= 120,user,bet,player_cards,bot_cards,playing_deck,client,display_bot_points,display_bot_cards):
        super().__init__(timeout=timeout)
        self.command_interaction = user
        self.bet = bet
        self.player_cards = player_cards
        self.bot_cards = bot_cards
        self.playing_deck = playing_deck
        self.bot = client
        self.display_bot_points = display_bot_points
        self.display_bot_cards = display_bot_cards
        self.cake_emoji = self.bot.get_emoji(common.cake_emoji_id)

    @discord.ui.button(label="拿牌!",style=discord.ButtonStyle.green)
    async def hit_button(self,interaction,button: discord.ui.Button):
        async with common.jsonio_lock:
            data = common.dataload()
            #關閉雙倍下注
            self.double_button.disabled = True
            #加牌
            BlackJack(self.bot).deal_card(self,self.playing_deck,self.player_cards)

            message = Embed(title="Natalie 21點",description="",color=common.bot_color)
            message.add_field(name=f"你的手牌點數:**{BlackJack(self.bot).calculate_point(self.player_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.player_cards)}",inline=False)
            message.add_field(name=f"Natalie的手牌點數:**{self.display_bot_points}**",value=f"{self.display_bot_cards}",inline=False)
            
            #爆牌
            if BlackJack(self.bot).calculate_point(self.player_cards) > 21:
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
                self.hit_button.disabled = True
                self.stand_button.disabled = True
                data[str(interaction.user.id)]["blackjack_playing"] = False
                data[str(interaction.user.id)]["blackjack_round"] += 1
                self.stop()
            #過五關
            elif len(self.player_cards) >= 5:
                data[str(interaction.user.id)]['cake'] += int(self.bet + (self.bet*3))
                data[str(interaction.user.id)]["blackjack_win_rate"] += 1
                message.add_field(name="結果",value=f"**過五關!**\n你獲得了**{int(self.bet*3)}**塊{self.cake_emoji}(過五關 x 3.0)\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
                self.hit_button.disabled = True
                self.stand_button.disabled = True
                data[str(interaction.user.id)]["blackjack_playing"] = False
                data[str(interaction.user.id)]["blackjack_round"] += 1
                self.stop()


            common.datawrite(data)
            message.set_footer(text=BlackJack(self.bot).win_rate_show(str(interaction.user.id)))
            await interaction.response.edit_message(embed=message,view=self)
            

    @discord.ui.button(label="停牌!",style=discord.ButtonStyle.red)
    async def stand_button(self,interaction,button: discord.ui.Button):
        async with common.jsonio_lock:
            data = common.dataload()
            #關閉所有按鈕
            self.double_button.disabled = True
            self.hit_button.disabled = True
            self.stand_button.disabled = True

            #莊家點數未達17點的話，則加牌直到點數>=17點
            while BlackJack(self.bot).calculate_point(self.bot_cards) < 17:
                BlackJack(self.bot).deal_card(self,self.playing_deck,self.bot_cards)
            
            message = Embed(title="Natalie 21點",description="",color=common.bot_color)
            message.add_field(name=f"你的手牌點數:**{BlackJack(self.bot).calculate_point(self.player_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.player_cards)}",inline=False)
            message.add_field(name=f"Natalie的手牌點數:**{BlackJack(self.bot).calculate_point(self.bot_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.bot_cards)}",inline=False) 
            data[str(interaction.user.id)]["blackjack_round"] += 1

            #莊家爆牌或者莊家點數比玩家小
            if BlackJack(self.bot).calculate_point(self.bot_cards) > 21 or (BlackJack(self.bot).calculate_point(self.bot_cards) < BlackJack(self.bot).calculate_point(self.player_cards)):
                data[str(interaction.user.id)]['cake'] += self.bet * 2
                data[str(interaction.user.id)]["blackjack_win_rate"] += 1
                message.add_field(name="結果",value=f"你贏了!\n你獲得了**{self.bet}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
                   
            #莊家的牌比玩家大
            if (BlackJack(self.bot).calculate_point(self.bot_cards) > BlackJack(self.bot).calculate_point(self.player_cards)) and BlackJack(self.bot).calculate_point(self.bot_cards) <= 21:
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)

            #平手
            if (BlackJack(self.bot).calculate_point(self.bot_cards) == BlackJack(self.bot).calculate_point(self.player_cards)) and BlackJack(self.bot).calculate_point(self.bot_cards) <= 21:
                data[str(interaction.user.id)]['cake'] += self.bet
                data[str(interaction.user.id)]["blackjack_tie"] += 1
                message.add_field(name="結果",value=f"平手!\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
            
            data[str(interaction.user.id)]["blackjack_playing"] = False
            common.datawrite(data)
            message.set_footer(text=BlackJack(self.bot).win_rate_show(str(interaction.user.id)))
            await interaction.response.edit_message(embed=message,view=self)
            self.stop()

    @discord.ui.button(label="雙倍下注!",style=discord.ButtonStyle.gray)
    async def double_button(self,interaction,button: discord.ui.Button):
        async with common.jsonio_lock:
            data = common.dataload()
            #如果賭注不足以使用雙倍下注
            if data[str(interaction.user.id)]['cake'] < self.bet:
                self.double_button.disabled = True
                self.double_button.label = "雙倍下注!(蛋糕不足)"
                await interaction.response.edit_message(view=self)
                return

            #關閉所有按鈕
            self.double_button.disabled = True
            self.hit_button.disabled = True
            self.stand_button.disabled = True

            #雙倍下注要扣的蛋糕
            data[str(interaction.user.id)]['cake'] -= self.bet
            #加牌
            BlackJack(self.bot).deal_card(self,self.playing_deck,self.player_cards)

            message = Embed(title="Natalie 21點",description="",color=common.bot_color)
            message.add_field(name=f"你的手牌點數:**{BlackJack(self.bot).calculate_point(self.player_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.player_cards)}",inline=False)
            data[str(interaction.user.id)]["blackjack_round"] += 1

            #玩家爆牌
            if BlackJack(self.bot).calculate_point(self.player_cards) > 21:
                message.add_field(name=f"Natalie的手牌點數:**{self.display_bot_points}**",value=f"{self.display_bot_cards}",inline=False)
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet*2}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
                data[str(interaction.user.id)]["blackjack_playing"] = False
                common.datawrite(data)
                message.set_footer(text=BlackJack(self.bot).win_rate_show(str(interaction.user.id)))
                await interaction.response.edit_message(embed=message,view=self)
                self.stop()
                return
            
            #莊家點數未達17點的話，則加牌直到點數>=17點
            while BlackJack(self.bot).calculate_point(self.bot_cards) < 17:
                BlackJack(self.bot).deal_card(self,self.playing_deck,self.bot_cards)

            message.add_field(name=f"Natalie的手牌點數:**{BlackJack(self.bot).calculate_point(self.bot_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.bot_cards)}",inline=False)

            #莊家爆牌或者莊家點數比玩家小
            if BlackJack(self.bot).calculate_point(self.bot_cards) > 21 or (BlackJack(self.bot).calculate_point(self.bot_cards) < BlackJack(self.bot).calculate_point(self.player_cards)):
                data[str(interaction.user.id)]['cake'] += self.bet * 4
                data[str(interaction.user.id)]["blackjack_win_rate"] += 1
                message.add_field(name="結果",value=f"你贏了!\n你獲得了**{self.bet*2}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
            
            #莊家的牌比玩家大
            if (BlackJack(self.bot).calculate_point(self.bot_cards) > BlackJack(self.bot).calculate_point(self.player_cards)) and BlackJack(self.bot).calculate_point(self.bot_cards) <= 21:
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet*2}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)

            #平手
            if (BlackJack(self.bot).calculate_point(self.bot_cards) == BlackJack(self.bot).calculate_point(self.player_cards)) and BlackJack(self.bot).calculate_point(self.bot_cards) <= 21:
                data[str(interaction.user.id)]['cake'] += self.bet * 2
                data[str(interaction.user.id)]["blackjack_tie"] += 1
                message.add_field(name="結果",value=f"平手!\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
            
            data[str(interaction.user.id)]["blackjack_playing"] = False
            common.datawrite(data)
            message.set_footer(text=BlackJack(self.bot).win_rate_show(str(interaction.user.id)))
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
        return "、".join([f"{r}{s}" for r, s in cards])

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
            + "\n最好牌型:" + pg.show_cards(player_best),
            inline=False,
        )
        message.add_field(
            name=f"Natalie的手牌(牌型:{bot_rank})",
            value=pg.show_cards(self.bot_cards)
            + "\n最好牌型:" + pg.show_cards(bot_best),
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
    """Strategy for deciding which hand the bot should keep."""

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
