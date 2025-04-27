import discord
from discord import Embed
from discord.ext import commands
import os
import aiohttp

class Natalie(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="C!",intents=discord.Intents().all())

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not(filename == 'common.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        await client.tree.sync()

    async def close(self):
        await super().close()
        await self.session.close()

    async def on_ready(self):
        print("機器人已啟動。")
        await client.get_channel(admin_log_channel).send(embed=Embed(title="系統操作",description="機器人已啟動。",color=bot_color))
        await client.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="偽造妹妹"))
#-------------------------------------
#全域參數列表
bot_color = 0x00DFEB #embed顏色
admin_log_channel = 543641756042788864   #admin日誌ID
mod_log_channel = 1062348474152136714    #管理員日誌ID
bot_owner_id = 410847926236086272 #我的ID
#-------------------------------------

client = Natalie()
# 從檔案中讀取token字串
with open("token.txt", "r") as f:
    token = f.read()
client.run(token)