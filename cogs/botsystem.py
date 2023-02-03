import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
import os
import time
import asyncio

class BotSystem(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.restart_time = 0
        self.gaming_time = 0

    
    @app_commands.command(name="shutdown", description = "關閉機器人" )
    async def shutdown(self,interaction):
        if interaction.user.id == common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作",description="我要睡著了...",color=common.bot_color))
            await self.bot.close()
        else: 
            await interaction.response.send_message(embed=Embed(title="系統操作",description="權限不足。",color=common.bot_color))

    
    @app_commands.command(name = "restart", description = "重新載入所有模組")
    async def restart(self,interaction):
        if interaction.user.id == common.bot_owner_id:
            data = common.dataload()

            await interaction.response.send_message(embed=Embed(title="系統操作",description="正在重新載入...",color=common.bot_color))
            #如果15秒內有人使用過具等待時間的指令(EX:mining)，則等待15秒
            if time.time() - data['gaming_time'] <= 15:
                #紀錄重啟的時間 
                data['restart_time'] = time.time()
                common.datawrite(data)
                await asyncio.sleep(15)
                
            for filename in os.listdir('./cogs'):
                if filename.endswith('.py') and not(filename == 'common.py'):
                    await self.bot.reload_extension(f'cogs.{filename[:-3]}')
            await self.bot.tree.sync()
            await interaction.followup.send(embed=Embed(title="系統操作",description="載入完成!",color=common.bot_color))
        else:
            await interaction.followup.send(embed=Embed(title="系統操作",description="權限不足。",color=common.bot_color))




async def setup(client:commands.Bot):
    await client.add_cog(BotSystem(client))