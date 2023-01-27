import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
import json
import random
import asyncio



class MiningGame(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.pickaxe_list = {
        "基本礦鎬": {"耐久度": 100, "需求等級": "無", "價格": "無"},
        "石鎬": {"耐久度": 200, "需求等級": 3, "價格": 150},
        "鐵鎬": {"耐久度": 400, "需求等級": 6, "價格": 2000},
        "鑽石鎬": {"耐久度": 650, "需求等級": 10, "價格": 4500},
        "不要鎬": {"耐久度": 1000, "需求等級": 18, "價格": 10000}
        }
        self.mineral_chancelist = {
        "森林礦坑": {"石頭": 0.3, "鐵": 0.45, "金": 0.25, "鈦晶": 0, "鑽石": 0},
        "荒野高原": {"石頭": 0.1, "鐵": 0.4, "金": 0.3, "鈦晶": 0.2, "鑽石": 0},
        "蛋糕仙境": {"石頭": 0, "鐵": 0.3, "金": 0.4, "鈦晶": 0.25, "鑽石": 0.05},
        "永世凍土": {"石頭": 0, "鐵": 0.2, "金": 0.4, "鈦晶": 0.3, "鑽石": 0.1},
        "熾熱火炎山": {"石頭": 0, "鐵": 0, "金": 0.4, "鈦晶": 0.3, "鑽石": 0.3}
        }
        self.collection_list = {
        "森林礦坑": ["昆蟲化石", "遠古的妖精翅膀", "萬年神木之根", "古代陶器碎片"],
        "荒野高原": ["風的根源石", "儀式石碑", "被詛咒的匕首", "神祕骷髏項鍊"],
        "蛋糕仙境": ["不滅的蠟燭", "蛋糕製造機", "異界之門鑰匙"],
        "永世凍土": ["雪怪排泄物", "冰鎮草莓甜酒"],
        "熾熱火炎山": ["上古琥珀", "火龍遺骨", "地獄辣炒年糕"]
        }
        self.mineral_pricelist = {
            "鐵": 10,
            "金": 30,
            "鈦晶": 70,
            "鑽石": 150
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

        return data


    @app_commands.command(name = "mining", description = "挖礦!")
    @app_commands.checks.cooldown(1, 15)
    async def mining(self,interaction):
        userid = str(interaction.user.id)
        user_data = common.dataload()
        mining_data = self.miningdata_read(userid)
        userlevel = common.LevelSystem().read_info(userid)

        #確認礦鎬壞了沒
        if mining_data[userid]["pickaxe_health"] == 0:
            if mining_data[userid]["autofix"] == True:
                mining_data[userid]["pickaxe_health"] = mining_data[userid]["pickaxe_maxhealth"]
                #user_data[userid]["cake"] -= 10
            else:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的礦鎬已經壞了!",color=common.bot_error_color))
                return

        mining_data[userid]["pickaxe_health"] -=10
        await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="正在挖礦中...",color=common.bot_color))
        await asyncio.sleep(15)

        #開始抽獎
        reward_probabilities = self.mineral_chancelist[mining_data[userid]["mine"]]
        print(f"debug:reward_probabilities={reward_probabilities}")
        random_num = random.random()
        current_probability = 0
        for reward, probability in reward_probabilities.items():
            print(f"當前reward:{reward},當前probability:{probability}")
            current_probability += probability
            if random_num < current_probability:
                #抽出礦物
                print("已抽出礦物")
                message = Embed(title="Natalie 挖礦",description=f"你挖到了{reward}",color=common.bot_color)
                if reward != "石頭":
                    mining_data[userid][reward] +=1
                break
        print("開始抽收藏品")
        #開始抽收藏品(0.5%機會)
        random_num = random.random()
        if random_num < 0.005:
            collection = random.choice(self.collection_list[mining_data[userid]["mine"]])
            mining_data[userid]["collections"][collection] += 1
            message.add_field(name="找到收藏品!",value=f"獲得**{collection}**!",inline= False)
        print("爆裝檢測")
        #高風險礦場機率爆裝
        random_num = random.random()
        if random_num < 0.1 and mining_data[userid]["mine"] == "熾熱火炎山":
            mining_data[userid]["pickaxe_health"] = 0
            message.add_field(name="礦鎬意外損毀!",value="你在挖礦途中不小心把礦鎬弄壞了，需要修理。",inline= False)

        print(f"修改embed:{message}")
        await interaction.edit_original_response(embed=message)
        common.datawrite(mining_data,"data/mining.json")
        common.datawrite(user_data)


    @app_commands.command(name = "pickaxe_fix", description = "修理礦鎬(需要10塊蛋糕)")
    async def pickaxe_fix(self,interaction):
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
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"你的蛋糕不足!(需要10塊，你目前只有{user_data[userid]['cake']}塊",color=common.bot_error_color))
            return
        
        #修理要10蛋糕
        #user_data[userid]["cake"] -= 10
        mining_data[userid]["pickaxe_health"] = mining_data[userid]["pickaxe_maxhealth"]
        await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="修理完成",color=common.bot_color))
        common.datawrite(user_data)
        common.datawrite(mining_data,"data/mining.json")
        
    @app_commands.command(name = "pickaxe_autofix", description = "自動修理礦鎬設置(預設關閉)")
    async def pickaxe_autofix(self,interaction):
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
        userid = str(interaction.user.id)
        mining_data = self.miningdata_read(userid)
        message = Embed(title="Natalie 挖礦",color=common.bot_color)
        #計算賣出價
        total_price = 0
        mineral_sellinfo_show = ""
        for mineral, quantity in mining_data[userid].items():
            if mineral in self.mineral_pricelist:
                total_price += self.mineral_pricelist[mineral] * quantity
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
        message.add_field(name=f"你獲得了{total_price}塊蛋糕",value="",inline=False)
        await interaction.response.send_message(embed=message)


    @mining.error
    async def on_mining_error(self,interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"輸入太快了，妹妹頂不住!請在{int(error.retry_after)}秒後再試一次。",color=common.bot_error_color), ephemeral=True)


class AutofixButton(discord.ui.View):
    def __init__(self, *,timeout= 30):
        super().__init__(timeout=timeout)
    
    @discord.ui.button(label="關閉自動修理",style=discord.ButtonStyle.danger)
    async def autofix_button(self,interaction,button: discord.ui.Button):
        userid = str(interaction.user.id)
        data = common.dataload("data/mining.json")
        data[userid]["autofix"] = False
        common.datawrite(data,"data/mining.json")
        button.disabled = True
        await interaction.response.edit_message(embed=Embed(title="Natalie 挖礦",description="自動修理已關閉。",color=common.bot_color),view=self)

async def setup(client:commands.Bot):
    await client.add_cog(MiningGame(client))