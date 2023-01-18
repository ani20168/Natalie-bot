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

    def playerdata_check(self,userid: str):
        data = common.dataload("data/mining.json")
        if userid not in data:
            data[userid] = {"pickaxe": "基本礦鎬"}

    @app_commands.command(name = "mining", description = "挖礦!")
    @app_commands.checks.cooldown(1, 15)
    async def mining(self,interaction):
        mining_data = common.dataload("data/mining.json")



    @app_commands.error
    async def on_mining_error(self,interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(embed=Embed(title="Natalie 挖礦",description=f"輸入太快了，妹妹頂不住!請在{error.retry_after}後再試一次。"), ephemeral=True)

async def setup(client:commands.Bot):
    await client.add_cog(MiningGame(client))