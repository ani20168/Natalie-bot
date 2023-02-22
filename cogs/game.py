import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
import random
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
    @app_commands.checks.cooldown(1, 15)
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

        #挖礦時間15秒
        await asyncio.sleep(15)

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

        message = Embed(title="Natalie 挖礦",description="指令:\n/mining 挖礦\n/pickaxe_fix 修理礦鎬\n/pickaxe_autofix 自動修理礦鎬\n/mineral_sell 賣出礦物\n/collection_trade 收藏品交易\n/mine 更換礦場\n/pickaxe_buy 購買礦鎬\n/redeem_collection_role 兌換收藏品稱號\n(注意:本指令缺乏測試，兌換前建議\n先使用mining_info留下收藏品資料。)\n/mining_machine_info 關於自動挖礦機",color=common.bot_color)
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
        
    @app_commands.command(name = "collection_trade",description="販賣收藏品")
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
        message = Embed(title="自動挖礦機",description="你可以透過購買自動挖礦機來挖掘礦物，每小時會挖掘一次，挖到的礦物會直接列入玩家礦物清單。\n注意!!由於挖礦機火力太強，會破壞掉珍貴的收藏品，因此自動挖掘時'不會'獲得任何收藏品",color=common.bot_color)
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


    @app_commands.command(name = "blackjack", description = "21點!")
    @app_commands.describe(bet="要下多少賭注?(支援all以及輸入蛋糕數量)")
    @app_commands.rename(bet="賭注")
    async def blackjack(self,interaction,bet: str):
        async with common.jsonio_lock:
            data = common.dataload()
            userid = str(interaction.user.id)
            cake_emoji = self.bot.get_emoji(common.cake_emoji_id)
            
            #檢查上一局遊戲有沒有玩完
            if "blackjack_playing" in data[userid] and data[userid]["blackjack_playing"] == True:
                await interaction.response.send_message(embed=Embed(title="Natalie 21點",description="你現在有進行中的遊戲!",color=common.bot_error_color))
                return

            #檢查要下注的數據
            if bet == "all":
                if data[userid]['cake'] >= 1:
                    bet = data[userid]['cake']
                else:
                    await interaction.response.send_message(embed=Embed(title="Natalie 21點",description=f"你現在沒有任何{cake_emoji}，無法下注!",color=common.bot_error_color))
                    return
            elif bet.isdigit() and int(bet) >= 1:
                bet = int(bet)
            else:
                await interaction.response.send_message(embed=Embed(title="Natalie 21點",description=f"無效的數據。(輸入想賭注的{cake_emoji}數量，或者輸入all下注全部的{cake_emoji})",color=common.bot_error_color))
                return

            #檢查蛋糕是否足夠
            if data[userid]['cake'] < bet:
                await interaction.response.send_message(embed=Embed(title="Natalie 21點",description=f"{cake_emoji}不足，無法下注!",color=common.bot_error_color))
                return
            data[userid]['cake'] -= bet

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
                common.datawrite(data)
                await interaction.response.send_message(embed=message)
                return
            
            #選項給予
            await interaction.response.send_message(embed=message,view = BlackJackButton(user=interaction,bet=bet,player_cards=player_cards,bot_cards=bot_cards,playing_deck=playing_deck,client=self.bot,display_bot_points=display_bot_points,display_bot_cards=display_bot_cards))
            data[userid]["blackjack_playing"] = True
            common.datawrite(data)

    @app_commands.command(name = "blackjack_player_status", description = "手動更改玩家狀態")
    @app_commands.describe(member="要變更的成員")
    @app_commands.rename(member="成員")
    async def blackjack_player_status(self,interaction,member:discord.Member):
        async with common.jsonio_lock:
            if interaction.user.id != common.bot_owner_id:
                await interaction.response.send_message(embed=Embed(title="系統操作",description = "權限不足",color=common.bot_error_color))
                return
            data = common.dataload()
            data[str(member.id)]["blackjack_playing"] = False
            common.datawrite(data)
            await interaction.response.send_message(embed=Embed(title="系統操作",description =f"修改<@{member.id}>的blackjack_playing變數為False。",color=common.bot_color))

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
                self.stop()

            await interaction.response.edit_message(embed=message,view=self)
            common.datawrite(data)

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

            #莊家爆牌或者莊家點數比玩家小
            if BlackJack(self.bot).calculate_point(self.bot_cards) > 21 or (BlackJack(self.bot).calculate_point(self.bot_cards) < BlackJack(self.bot).calculate_point(self.player_cards)):
                data[str(interaction.user.id)]['cake'] += self.bet * 2
                message.add_field(name="結果",value=f"你贏了!\n你獲得了**{self.bet}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
            
            #莊家的牌比玩家大
            if (BlackJack(self.bot).calculate_point(self.bot_cards) > BlackJack(self.bot).calculate_point(self.player_cards)) and BlackJack(self.bot).calculate_point(self.bot_cards) <= 21:
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)

            #平手
            if (BlackJack(self.bot).calculate_point(self.bot_cards) == BlackJack(self.bot).calculate_point(self.player_cards)) and BlackJack(self.bot).calculate_point(self.bot_cards) <= 21:
                data[str(interaction.user.id)]['cake'] += self.bet
                message.add_field(name="結果",value=f"平手!\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
            
            data[str(interaction.user.id)]["blackjack_playing"] = False
            await interaction.response.edit_message(embed=message,view=self)
            common.datawrite(data)
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

            #玩家爆牌
            if BlackJack(self.bot).calculate_point(self.player_cards) > 21:
                message.add_field(name=f"Natalie的手牌點數:**{self.display_bot_points}**",value=f"{self.display_bot_cards}",inline=False)
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet*2}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
                await interaction.response.edit_message(embed=message,view=self)
                data[str(interaction.user.id)]["blackjack_playing"] = False
                common.datawrite(data)
                self.stop()
                return
            
            #莊家點數未達17點的話，則加牌直到點數>=17點
            while BlackJack(self.bot).calculate_point(self.bot_cards) < 17:
                BlackJack(self.bot).deal_card(self,self.playing_deck,self.bot_cards)

            message.add_field(name=f"Natalie的手牌點數:**{BlackJack(self.bot).calculate_point(self.bot_cards)}**",value=f"{BlackJack(self.bot).show_cards(self.bot_cards)}",inline=False)

            #莊家爆牌或者莊家點數比玩家小
            if BlackJack(self.bot).calculate_point(self.bot_cards) > 21 or (BlackJack(self.bot).calculate_point(self.bot_cards) < BlackJack(self.bot).calculate_point(self.player_cards)):
                data[str(interaction.user.id)]['cake'] += self.bet * 4
                message.add_field(name="結果",value=f"你贏了!\n你獲得了**{self.bet*2}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
            
            #莊家的牌比玩家大
            if (BlackJack(self.bot).calculate_point(self.bot_cards) > BlackJack(self.bot).calculate_point(self.player_cards)) and BlackJack(self.bot).calculate_point(self.bot_cards) <= 21:
                message.add_field(name="結果",value=f"你輸了!\n你失去了**{self.bet*2}**塊{self.cake_emoji}\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)

            #平手
            if (BlackJack(self.bot).calculate_point(self.bot_cards) == BlackJack(self.bot).calculate_point(self.player_cards)) and BlackJack(self.bot).calculate_point(self.bot_cards) <= 21:
                data[str(interaction.user.id)]['cake'] += self.bet * 2
                message.add_field(name="結果",value=f"平手!\n你現在擁有**{data[str(interaction.user.id)]['cake']}**塊{self.cake_emoji}",inline=False)
            
            await interaction.response.edit_message(embed=message,view=self)
            data[str(interaction.user.id)]["blackjack_playing"] = False
            common.datawrite(data)
            self.stop()

    async def interaction_check(self, interaction) -> bool:
        data = common.dataload()
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