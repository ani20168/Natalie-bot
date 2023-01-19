import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta
import json




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


    def miningdata_read(self,userid: str):
        data = common.dataload("data/mining.json")

        if userid not in data:
            data[userid] = {
                "pickaxe": "基本礦鎬",
                "mine": "森林礦坑",
                "pickaxe_health": 100,
                "pickaxe_maxhealth": 100,
                "autofix": False
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

        if mining_data[userid]["pickaxe_health"] == 0:
            if mining_data[userid]["autofix"] == True:
                mining_data[userid]["pickaxe_health"] = mining_data[userid]["pickaxe_maxhealth"]
                #user_data[userid]["cake"] -= 10
            else:
                await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你的礦鎬已經壞了!",color=common.bot_error_color))
                return

        mining_data[userid]["pickaxe_health"] -=10
        await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"test:礦鎬耐久 {mining_data[userid]['pickaxe_health']}",color=common.bot_color))
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
        """
        if data[userid]["autofix"] == False:
            data[userid]["autofix"] = True
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="自動修理已開啟。\n在耐久不足時會自動消耗蛋糕進行修理。",color=common.bot_color))
            common.datawrite(data,"data/mining.json")
            return
        """
        if data[userid]["autofix"] == True:
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description="你已經開啟了自動修理礦鎬。",color=common.bot_color),ephemeral=True,view=AutofixButton())




    @mining.error
    async def on_mining_error(self,interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"輸入太快了，妹妹頂不住!請在{int(error.retry_after)}秒後再試一次。",color=common.bot_error_color), ephemeral=True)


class AutofixButton(discord.ui.View):
    def __init__(self, *,timeout= 20):
        super().__init__(timeout=timeout)
    
    @discord.ui.button(label="關閉自動修理",style=discord.ButtonStyle.danger)
    async def autofix_button(self,interaction,button: discord.ui.Button):
        userid = str(interaction.user.id)
        data = common.dataload("data/mining.json")
        data[userid]["autofix"] = False
        common.datawrite(data,"data/mining.json")
        button.disabled = True
        await interaction.response.edit_message(embed=Embed(title="Natalie 挖礦",description="自動修理已關閉。",color=common.bot_color),view=self)
        

    async def on_timeout(self,interaction) -> None:
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

async def setup(client:commands.Bot):
    await client.add_cog(MiningGame(client))