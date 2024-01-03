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
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作",description="權限不足。",color=common.bot_error_color))
            return
        
        await self.restart_service()

        # if interaction.user.id == common.bot_owner_id:
        #     data = common.dataload()

        #     #如果有玩家正在玩blackjack
        #     blackjack_playing_status_message = ""
        #     for member_id, member_info in data.items():
        #         if isinstance(member_info, dict) and member_info.get("blackjack_playing") == True:
        #             blackjack_playing_status_message += self.bot.get_user(int(member_id)).display_name + "\n"
        #     if blackjack_playing_status_message != "":
        #         await interaction.response.send_message(embed=Embed(title="系統操作",description=f"暫時無法重啟，以下用戶正在玩「BlackJack」!\n{blackjack_playing_status_message}",color=common.bot_error_color))
        #         return

        #     #如果15秒內有人使用過具等待時間的指令(EX:mining)，則等待15秒
        #     if time.time() - data['gaming_time'] <= 15:
        #         #紀錄重啟的時間 
        #         data['restart_time'] = time.time()
        #         common.datawrite(data)
        #         await interaction.response.send_message(embed=Embed(title="系統操作",description="15秒後重新載入...(正在等待其他指令執行完畢)",color=common.bot_color))
        #         await asyncio.sleep(15)
        #     else:
        #         await interaction.response.send_message(embed=Embed(title="系統操作",description="正在重新載入...",color=common.bot_color))

        #     for filename in os.listdir('./cogs'):
        #         if filename.endswith('.py') and not(filename == 'common.py'):
        #             await self.bot.reload_extension(f'cogs.{filename[:-3]}')
        #     await self.bot.tree.sync()
        #     await interaction.followup.send(embed=Embed(title="系統操作",description="載入完成!",color=common.bot_color))
        # else:
        #     await interaction.followup.send(embed=Embed(title="系統操作",description="權限不足。",color=common.bot_color))

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
                await self.bot.get_channel(543641756042788864).send(embed=Embed(title="系統操作",description=f"暫時無法重啟，以下用戶正在玩「BlackJack」!\n{blackjack_playing_status_message}",color=common.bot_error_color))
                return

            
            #如果15秒內有人使用過具等待時間的指令(EX:mining)，則等待15秒
            if time.time() - data['gaming_time'] <= 15:
                need_to_wait = True
                #紀錄重啟的時間 
                data['restart_time'] = time.time()
                common.datawrite(data)

        if need_to_wait:
            await self.bot.get_channel(543641756042788864).send(embed=Embed(title="系統操作",description="15秒後重新載入...(正在等待其他指令執行完畢)",color=common.bot_color))
            await asyncio.sleep(15)

        await self.bot.get_channel(543641756042788864).send(embed=Embed(title="系統操作",description="正在重新載入...",color=common.bot_color))
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not(filename == 'common.py'):
                await self.bot.reload_extension(f'cogs.{filename[:-3]}')
        await self.bot.tree.sync()
        await self.bot.get_channel(543641756042788864).send(embed=Embed(title="系統操作",description="載入完成!",color=common.bot_color))




async def setup(client:commands.Bot):
    await client.add_cog(BotSystem(client))