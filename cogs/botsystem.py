import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
import os
import time
import asyncio
from typing import Optional

class BotSystem(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.auto_restart.start()

    async def cog_unload(self):
        self.auto_restart.cancel()
        await asyncio.to_thread(common.mongo_storage.close_client)

    
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
        data = await common.mongo_storage.load_data_from_mongo()
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
            await common.mongo_storage.update_global_fields({"restart_time": time.time()})

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

    @app_commands.command(name="backup_db", description="在伺服器匯出 MongoDB 備份檔")
    @app_commands.describe(output_dir="備份輸出目錄，預設為 data/backup/")
    async def backup_db(self, interaction: discord.Interaction, output_dir: Optional[str] = None):
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作", description="權限不足。", color=common.bot_error_color))
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        backup_dir = output_dir.strip() if output_dir else "data/backup/"
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_filename = f"discord_{timestamp}.tar.gz"
        backup_path = os.path.join(backup_dir, backup_filename)
        latest_path_file = os.path.join(backup_dir, "latest_backup.txt")

        if not common.mongo_storage.get_mongo_uri():
            await interaction.followup.send(embed=Embed(title="備份失敗", description="找不到 Mongo 連線設定（請檢查 secret.json 的 DB_URL 與 PRD_DB_URL）。", color=common.bot_error_color), ephemeral=True)
            return

        try:
            summary = await common.mongo_storage.export_database_backup(backup_path)
        except Exception as error:
            await interaction.followup.send(embed=Embed(title="備份失敗", description=f"{type(error).__name__}: {error}", color=common.bot_error_color), ephemeral=True)
            return

        with open(latest_path_file, "w", encoding="utf-8") as file:
            file.write(f"{backup_path}\n")

        backup_size = os.path.getsize(backup_path) if os.path.isfile(backup_path) else 0
        collection_lines = "\n".join(f"- `{item['name']}`: {item['document_count']} 筆" for item in summary["collections"])
        success_message = (
            f"資料庫: `{summary['database']}`\n"
            f"格式: `{summary['format']}`\n"
            f"總文件數: `{summary['document_count']}`\n"
            f"{collection_lines}\n"
            f"備份檔案: `{backup_filename}`\n"
            f"完整路徑: `{backup_path}`\n"
            f"檔案大小: `{backup_size}` bytes\n"
            f"latest 標記: `{latest_path_file}`"
        )
        await interaction.followup.send(embed=Embed(title="資料庫備份完成", description=success_message, color=common.bot_color), ephemeral=True)

    @app_commands.command(name="restore_db", description="從備份檔還原 MongoDB 資料庫")
    @app_commands.describe(
        backup_path="備份檔路徑，預設為 data/backup/discord_latest.tar.gz",
        drop_existing="是否先清空同名 collection（預設否）",
    )
    async def restore_db(self, interaction: discord.Interaction, backup_path: Optional[str] = None, drop_existing: bool = False):
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作", description="權限不足。", color=common.bot_error_color))
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        target_backup_path = backup_path.strip() if backup_path else "data/backup/discord_latest.tar.gz"
        if not os.path.isfile(target_backup_path):
            await interaction.followup.send(embed=Embed(title="還原失敗", description=f"找不到備份檔：`{target_backup_path}`", color=common.bot_error_color), ephemeral=True)
            return

        try:
            summary = await common.mongo_storage.restore_database_backup(target_backup_path, drop_existing=drop_existing)
        except Exception as error:
            await interaction.followup.send(embed=Embed(title="還原失敗", description=f"{type(error).__name__}: {error}", color=common.bot_error_color), ephemeral=True)
            return

        collection_lines = "\n".join(f"- `{item['name']}`: {item['document_count']} 筆" for item in summary["collections"])
        success_message = (
            f"資料庫: `{summary['database']}`\n"
            f"格式: `{summary['format']}`\n"
            f"總文件數: `{summary['document_count']}`\n"
            f"清空舊資料: `{summary['drop_existing']}`\n"
            f"{collection_lines}\n"
            f"來源備份: `{target_backup_path}`"
        )
        await interaction.followup.send(embed=Embed(title="資料庫還原完成", description=success_message, color=common.bot_color), ephemeral=True)



async def setup(client:commands.Bot):
    await client.add_cog(BotSystem(client))