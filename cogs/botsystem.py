import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
import os
import time
import asyncio
from typing import Optional

class BotSystem(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        # 重啟準備旗標；機器人啟動時一律清除（新行程載入時為 False）
        self.restart_pending = False
        self.bot.tree.interaction_check = self.check_not_restarting

    async def cog_unload(self):
        await asyncio.to_thread(common.mongo_storage.close_client)

    async def check_not_restarting(self, interaction: discord.Interaction) -> bool:
        """
        重啟 flag 開啟時阻擋所有 slash 指令，並回覆提示 embed。

        Args:
            interaction (discord.Interaction): "slash 指令互動"

        Returns:
            allowed (bool): "True"
        """
        if not self.restart_pending:
            return True
        embed = Embed(
            title="Natalie 正在準備重新啟動...",
            description="過幾分鐘後再來吧!",
            color=common.bot_error_color,
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)
        return False

    @app_commands.command(name="restart", description="標記機器人準備重新啟動")
    async def restart(self, interaction: discord.Interaction):
        """
        設定重啟 flag，之後所有指令會提示正在準備重啟。

        Args:
            interaction (discord.Interaction): "slash 指令互動"
        """
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作", description="權限不足。", color=common.bot_error_color))
            return
        self.restart_pending = True
        await interaction.response.send_message(embed=Embed(title="系統操作", description="已標記準備重新啟動，之後所有指令將暫時無法使用。", color=common.bot_color))
        await self.bot.get_channel(common.admin_log_channel).send(embed=Embed(title="系統操作", description="重啟 flag 已開啟，等待 CI/CD 重新部署。", color=common.bot_color))

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
