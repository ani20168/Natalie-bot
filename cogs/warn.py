import discord
from discord import app_commands, Embed
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from typing import Optional

from dateutil.parser import parse

from . import common


class WarnDeleteConfirmView(discord.ui.View):
    """刪除警告前的確認介面，逾時後停用按鈕。"""

    def __init__(self, invoker_id: int, target_user_id: int, index_one_based: int):
        super().__init__(timeout=20.0)
        self.invoker_id = invoker_id
        self.target_user_id = target_user_id
        self.index_one_based = index_one_based
        self.confirm_message: discord.Message | None = None
        self.add_item(WarnDeleteConfirmButton())

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.confirm_message is None:
            return
        try:
            await self.confirm_message.edit(view=self)
        except discord.HTTPException:
            pass


class WarnDeleteConfirmButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="確認刪除", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: WarnDeleteConfirmView = self.view  # type: ignore[assignment]
        if interaction.user.id != view.invoker_id:
            await interaction.response.send_message(
                embed=Embed(title="刪除警告", description="只有使用指令的人才能確認刪除。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        target_key = str(view.target_user_id)
        idx = view.index_one_based - 1
        error_key: str | None = None
        async with common.jsonio_lock:
            data = common.dataload()
            user_block = data.get(target_key)
            if not isinstance(user_block, dict):
                error_key = "no_user"
            else:
                warn_list = user_block.get("warn_list")
                if not isinstance(warn_list, list) or idx < 0 or idx >= len(warn_list):
                    error_key = "bad_idx"
                else:
                    del warn_list[idx]
                    common.datawrite(data)
        if error_key == "no_user":
            await interaction.response.send_message(
                embed=Embed(title="刪除警告", description="找不到該使用者的資料。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        if error_key == "bad_idx":
            await interaction.response.send_message(
                embed=Embed(title="刪除警告", description="該序號已不存在或資料已變更。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        done_embed = Embed(title="刪除警告", description=f"已刪除 <@{view.target_user_id}> 第 **{view.index_one_based}** 筆警告紀錄。", color=common.bot_color)
        await interaction.response.edit_message(embed=done_embed, view=None)


class Warn(commands.Cog):
    warn_valid_days = 183

    def __init__(self, client: commands.Bot):
        self.bot = client

    @staticmethod
    def parse_warn_timestamp(raw: str) -> datetime:
        """將 warn 紀錄的時間字串轉成 UTC 的 datetime 以便比較。"""
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            dt = parse(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def format_warn_time(utc_dt: datetime) -> str:
        """將 UTC 時間轉成 UTC+8 顯示字串。"""
        return utc_dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

    @classmethod
    def count_effective_warns(cls, warn_list: list, now_utc: datetime) -> int:
        """統計半年內（未過期）的警告筆數。"""
        cutoff = now_utc - timedelta(days=cls.warn_valid_days)
        count = 0
        for entry in warn_list:
            if not isinstance(entry, dict) or "timestamp" not in entry:
                continue
            try:
                entry_time = cls.parse_warn_timestamp(str(entry["timestamp"]))
            except (ValueError, TypeError, OverflowError):
                continue
            if entry_time >= cutoff:
                count += 1
        return count

    @app_commands.command(name="warn", description="給予成員警告（僅管理員）")
    @app_commands.describe(member="被警告的成員", reason="理由")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(
                embed=Embed(title="警告", description="權限不足。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        if member.bot:
            await interaction.response.send_message(
                embed=Embed(title="警告", description="無法對機器人發出警告。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        target_key = str(member.id)
        now_utc = datetime.now(timezone.utc)
        ts_str = now_utc.isoformat()
        async with common.jsonio_lock:
            data = common.dataload()
            if target_key not in data:
                data[target_key] = {"cake": 0, "warn_list": []}
            elif not isinstance(data[target_key], dict):
                data[target_key] = {"cake": 0, "warn_list": []}
            user_block = data[target_key]
            if "warn_list" not in user_block or not isinstance(user_block["warn_list"], list):
                user_block["warn_list"] = []
            user_block["warn_list"].insert(0, {"reason": reason, "timestamp": ts_str})
            common.datawrite(data)
            warn_list = user_block["warn_list"]
            total = len(warn_list)
            effective = self.count_effective_warns(warn_list, now_utc)
        dm_embed = Embed(
            title="你收到一則警告",
            description=f"理由：{reason}",
            color=common.bot_error_color,
        )
        dm_embed.set_footer(text="可使用 `warnlist` 查看自己的警告紀錄")
        dm_ok = True
        try:
            await member.send(embed=dm_embed)
        except discord.HTTPException:
            dm_ok = False
        desc = f"已警告 <@{member.id}>。\n有效警告總數（半年內）：**{effective}**\n總警告數：**{total}**"
        if not dm_ok:
            desc += "\n（無法傳送私人訊息給該成員，請對方開啟伺服器成員私訊。）"
        await interaction.response.send_message(embed=Embed(title="警告", description=desc, color=common.bot_color), ephemeral=True)

    @app_commands.command(name="warnlist", description="查看警告紀錄")
    @app_commands.describe(member="要查詢的成員（僅管理員）")
    async def warnlist(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        if member is not None and member.bot:
            await interaction.response.send_message(
                embed=Embed(title="警告紀錄", description="無法查詢機器人的警告紀錄。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        target = member if member is not None else interaction.user
        if target.bot:
            await interaction.response.send_message(
                embed=Embed(title="警告紀錄", description="無法查詢機器人的警告紀錄。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        if member is not None and target.id != interaction.user.id and interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(
                embed=Embed(title="警告紀錄", description="權限不足：僅擁有者可查詢他人的警告紀錄。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        data = common.dataload()
        target_key = str(target.id)
        user_block = data.get(target_key)
        warn_list: list = []
        if isinstance(user_block, dict) and isinstance(user_block.get("warn_list"), list):
            warn_list = user_block["warn_list"]
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=self.warn_valid_days)
        effective = self.count_effective_warns(warn_list, now_utc)
        total = len(warn_list)
        lines: list[str] = []
        for serial, entry in enumerate(warn_list, start=1):
            if not isinstance(entry, dict):
                line = f"{serial}. （資料格式異常）"
            else:
                reason_text = str(entry.get("reason", "（無理由）"))
                ts_raw = entry.get("timestamp", "")
                try:
                    entry_time = self.parse_warn_timestamp(str(ts_raw))
                    time_text = self.format_warn_time(entry_time)
                    expired_note = "（已過期的紀錄）" if entry_time < cutoff else ""
                except (ValueError, TypeError, OverflowError):
                    time_text = str(ts_raw)
                    expired_note = ""
                line = f"{serial}. {reason_text}\n　時間：{time_text}{expired_note}"
            lines.append(line)
        body = "\n\n".join(lines) if lines else "尚無警告紀錄。"
        embed = Embed(title=f"{target.display_name} 的警告紀錄", description=body, color=common.bot_color)
        embed.set_footer(text=f"有效警告總數：{effective}｜總警告數：{total}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="warn_delete", description="刪除成員的警告紀錄（僅管理員）")
    @app_commands.describe(member="成員", index="序號（1＝最新一筆，由新到舊）")
    async def warn_delete(self, interaction: discord.Interaction, member: discord.Member, index: int) -> None:
        if interaction.user.id != common.bot_owner_id:
            await interaction.response.send_message(
                embed=Embed(title="刪除警告", description="權限不足。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        target_key = str(member.id)
        data = common.dataload()
        user_block = data.get(target_key)
        warn_list: list = []
        if isinstance(user_block, dict) and isinstance(user_block.get("warn_list"), list):
            warn_list = user_block["warn_list"]
        if not warn_list:
            await interaction.response.send_message(
                embed=Embed(title="刪除警告", description="該成員沒有任何警告紀錄。", color=common.bot_error_color),
                ephemeral=True,
            )
            return
        if index < 1 or index > len(warn_list):
            await interaction.response.send_message(
                embed=Embed(
                    title="刪除警告",
                    description=f"序號無效（目前共有 **{len(warn_list)}** 筆紀錄，請輸入 1～{len(warn_list)}）。",
                    color=common.bot_error_color,
                ),
                ephemeral=True,
            )
            return
        entry = warn_list[index - 1]
        reason_preview = str(entry.get("reason", "（無理由）")) if isinstance(entry, dict) else "（無資料）"
        ts_raw = entry.get("timestamp", "") if isinstance(entry, dict) else ""
        try:
            entry_time = self.parse_warn_timestamp(str(ts_raw))
            time_preview = self.format_warn_time(entry_time)
        except (ValueError, TypeError, OverflowError):
            time_preview = str(ts_raw)
        preview = Embed(
            title="確認刪除警告",
            description=f"對象：<@{member.id}>\n序號：**{index}**\n理由：{reason_preview}\n時間：{time_preview}\n\n按下「確認刪除」後才會從資料中移除。",
            color=common.bot_error_color,
        )
        view = WarnDeleteConfirmView(interaction.user.id, member.id, index)
        await interaction.response.send_message(embed=preview, view=view)
        view.confirm_message = await interaction.original_response()


async def setup(client: commands.Bot) -> None:
    await client.add_cog(Warn(client))
