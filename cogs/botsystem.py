import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
import os
import time
import asyncio

class BotSystem(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.auto_restart.start()

    async def cog_unload(self):
        self.auto_restart.cancel()

    
    @app_commands.command(name="shutdown", description = "關閉機器人" )
    async def shutdown(self,interaction):
        if interaction.user.id == common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作",description="我要睡著了...",color=common.bot_color))
            await self.bot.close()
        else: 
            await interaction.response.send_message(embed=Embed(title="系統操作",description="權限不足。",color=common.bot_color))

    
    @app_commands.command(name = "restart", description = "重新載入所有模組")
    async def restart(self,interaction):
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作",description="權限不足。",color=common.bot_error_color))
            return
        await interaction.response.send_message(embed=Embed(title="系統操作",description="嘗試運行重啟服務...",color=common.bot_color))
        await self.restart_service()

    async def restart_service(self):
        need_to_wait = False
        async with common.jsonio_lock:
            data = common.dataload()
            #如果有玩家正在玩blackjack
            blackjack_playing_status_message = ""
            for member_id, member_info in data.items():
                if isinstance(member_info, dict) and member_info.get("blackjack_playing") == True:
                    blackjack_playing_status_message += self.bot.get_user(int(member_id)).display_name + "\n"
            if blackjack_playing_status_message != "":
                await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="系統操作",description=f"暫時無法重啟，以下用戶正在玩「BlackJack」!\n{blackjack_playing_status_message}",color=common.bot_error_color))
                return

            
            #如果15秒內有人使用過具等待時間的指令(EX:mining)，則等待15秒
            if time.time() - data['gaming_time'] <= 15:
                need_to_wait = True
                #紀錄重啟的時間 
                data['restart_time'] = time.time()
                common.datawrite(data)

        if os.path.isfile('deploy_restart.txt'):
            with open('deploy_restart.txt', 'w') as file:
                file.write('0')
                
        if need_to_wait:
            await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="系統操作",description="15秒後重新載入...(正在等待其他指令執行完畢)",color=common.bot_color))
            await asyncio.sleep(15)

        await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="系統操作",description="正在重新載入...",color=common.bot_color))
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not(filename == 'common.py'):
                await self.bot.reload_extension(f'cogs.{filename[:-3]}')
        await self.bot.tree.sync()
        await asyncio.sleep(2) #加這個避免訊息發送太快被API吃掉
        await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="系統操作",description="載入完成!",color=common.bot_color))

    @tasks.loop(seconds=15)
    async def auto_restart(self):
        if not os.path.isfile('deploy_restart.txt'):
            return
        with open('deploy_restart.txt', 'r') as file:
            content = file.read().strip()
        if content == '1':
            await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="自動部署流程",description="收到新的版本，機器人將自動重啟。",color=common.bot_color))
            await self.restart_service()


    @auto_restart.before_loop
    async def event_before_loop(self):
        await self.bot.wait_until_ready()



async def setup(client:commands.Bot):
    await client.add_cog(BotSystem(client))