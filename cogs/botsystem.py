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

    @app_commands.command(name="migrate_json_to_mongo", description="將現有 JSON 資料遷移到 MongoDB")
    async def migrate_json_to_mongo(self, interaction: discord.Interaction):
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作", description="權限不足。", color=common.bot_error_color))
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            summary = await common.mongo_storage.migrate_json_to_mongo()
            summary_message = (
                f"資料庫: **{summary['database']}**\n"
                f"userdata 使用者文件: **{summary['userdata_user_count']}**\n"
                f"userdata 全域鍵: **{summary['userdata_global_count']}**\n"
                f"mining 使用者文件: **{summary['mining_user_count']}**\n"
                f"mining 全域鍵: **{summary['mining_global_count']}**\n"
                f"odds 鍵數: **{summary['odds_key_count']}**\n"
                f"全域文件 id: **{summary['global_document_id']}**"
            )
            await interaction.followup.send(embed=Embed(title="遷移完成", description=summary_message, color=common.bot_color), ephemeral=True)
        except Exception as error:
            await interaction.followup.send(embed=Embed(title="遷移失敗", description=f"{type(error).__name__}: {error}", color=common.bot_error_color), ephemeral=True)

    @app_commands.command(name="backup_db", description="在伺服器匯出 MongoDB 備份檔")
    @app_commands.describe(output_dir="備份輸出目錄，預設為 ./backup/mongo/")
    async def backup_db(self, interaction: discord.Interaction, output_dir: Optional[str] = None):
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作", description="權限不足。", color=common.bot_error_color))
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        backup_dir = output_dir.strip() if output_dir else "./backup/mongo/"
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_filename = f"discord_{timestamp}.archive.gz"
        backup_path = os.path.join(backup_dir, backup_filename)
        latest_path_file = os.path.join(backup_dir, "latest_backup.txt")

        mongo_uri = common.mongo_storage.get_mongo_uri()
        if not mongo_uri:
            await interaction.followup.send(embed=Embed(title="備份失敗", description="找不到 Mongo 連線設定（請檢查 secret.json 的 DB_URL 與 PRD_DB_URL）。", color=common.bot_error_color), ephemeral=True)
            return

        database_name = common.mongo_storage.get_database_name(mongo_uri)
        mongodump_binary = os.getenv("MONGODUMP_BIN", "mongodump")
        process = await asyncio.create_subprocess_exec(
            mongodump_binary,
            f"--uri={mongo_uri}",
            f"--db={database_name}",
            f"--archive={backup_path}",
            "--gzip",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error_message = stderr.decode("utf-8", errors="ignore").strip()
            if not error_message: error_message = stdout.decode("utf-8", errors="ignore").strip()
            if not error_message: error_message = "未知錯誤"
            await interaction.followup.send(embed=Embed(title="備份失敗", description=f"錯誤碼: {process.returncode}\n{error_message[:1800]}", color=common.bot_error_color), ephemeral=True)
            return

        with open(latest_path_file, "w", encoding="utf-8") as file:
            file.write(f"{backup_path}\n")

        backup_size = os.path.getsize(backup_path) if os.path.isfile(backup_path) else 0
        success_message = (
            f"備份檔案: `{backup_filename}`\n"
            f"完整路徑: `{backup_path}`\n"
            f"檔案大小: `{backup_size}` bytes\n"
            f"latest 標記: `{latest_path_file}`"
        )
        await interaction.followup.send(embed=Embed(title="資料庫備份完成", description=success_message, color=common.bot_color), ephemeral=True)



async def setup(client:commands.Bot):
    await client.add_cog(BotSystem(client))