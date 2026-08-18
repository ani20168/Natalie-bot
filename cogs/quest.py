import discord
from discord import app_commands, Embed
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
from pymongo import ReturnDocument

from . import common


class DailyQuest:
    """每日任務基底，新任務請繼承並覆寫屬性。"""

    def __init__(self) -> None:
        self.quest_id = ""
        self.description = ""
        self.cake_reward = 0
        self.marshmallow_reward = 0
        self.event_type = ""
        self.target = 1

    def matches_event(self, event_type: str) -> bool:
        """
        判斷此任務是否會被指定事件推進。

        Args:
            event_type (str): "lobby_chat"

        Returns:
            matched (bool): "True"
        """
        return self.event_type == event_type


class LobbyChat3Quest(DailyQuest):
    def __init__(self, lobby_channel_id: int) -> None:
        super().__init__()
        self.quest_id = "lobby_chat_3"
        self.description = f"在<#{lobby_channel_id}>發言超過3句話"
        self.cake_reward = 500
        self.marshmallow_reward = 1
        self.event_type = "lobby_chat"
        self.target = 3


class LobbyChat10Quest(DailyQuest):
    def __init__(self, lobby_channel_id: int) -> None:
        super().__init__()
        self.quest_id = "lobby_chat_10"
        self.description = f"在<#{lobby_channel_id}>發言超過10句話"
        self.cake_reward = 6500
        self.marshmallow_reward = 1
        self.event_type = "lobby_chat"
        self.target = 10


class Voice30MinQuest(DailyQuest):
    def __init__(self) -> None:
        super().__init__()
        self.quest_id = "voice_30m"
        self.description = "待在遊戲區語音房的時間超過30分鐘"
        self.cake_reward = 300
        self.marshmallow_reward = 1
        self.event_type = "game_voice"
        self.target = 30


class Voice2HourQuest(DailyQuest):
    def __init__(self) -> None:
        super().__init__()
        self.quest_id = "voice_2h"
        self.description = "待在遊戲區語音房的時間超過2小時"
        self.cake_reward = 2500
        self.marshmallow_reward = 1
        self.event_type = "game_voice"
        self.target = 120


class Voice5HourQuest(DailyQuest):
    def __init__(self) -> None:
        super().__init__()
        self.quest_id = "voice_5h"
        self.description = "待在遊戲區語音房的時間超過5小時"
        self.cake_reward = 10000
        self.marshmallow_reward = 2
        self.event_type = "game_voice"
        self.target = 300


class VoiceStream1HourQuest(DailyQuest):
    def __init__(self) -> None:
        super().__init__()
        self.quest_id = "voice_stream_1h"
        self.description = "在遊戲區語音房直播超過1小時"
        self.cake_reward = 5000
        self.marshmallow_reward = 1
        self.event_type = "game_voice_stream"
        self.target = 60


class InviteMemberQuest(DailyQuest):
    def __init__(self) -> None:
        super().__init__()
        self.quest_id = "invite_member"
        self.description = "成功邀請一個人進入妹妹群"
        self.cake_reward = 50000
        self.marshmallow_reward = 2
        self.event_type = "invite_member"
        self.target = 1


class BlackjackQuest(DailyQuest):
    def __init__(self) -> None:
        super().__init__()
        self.quest_id = "blackjack"
        self.description = "在21點獲得一次Blackjack!"
        self.cake_reward = 1000
        self.marshmallow_reward = 1
        self.event_type = "blackjack"
        self.target = 1


class SquidRpsHardWinQuest(DailyQuest):
    def __init__(self) -> None:
        super().__init__()
        self.quest_id = "squid_rps_hard_win"
        self.description = "在困難版的魷魚猜拳獲勝一場"
        self.cake_reward = 10000
        self.marshmallow_reward = 2
        self.event_type = "squid_rps_hard_win"
        self.target = 1


async def report_quest_event(bot: commands.Bot, user_id: str | int, event_type: str, amount: int = 1):
    """
    由其他 cog 呼叫：回報事件以推進對應每日任務。

    Args:
        bot (commands.Bot): "Natalie(...)"
        user_id (str | int): "410847926236086272"
        event_type (str): "blackjack"
        amount (int): "1"
    """
    cog = bot.get_cog("Quest")
    if cog is None: return
    try:
        await cog.report_event(str(user_id), event_type, amount)
    except Exception as error:
        print(f"quest report_event failed: {type(error).__name__}: {error}")


async def complete_user_quest(bot: commands.Bot, user_id: str | int, quest_id: str):
    """
    由其他 cog 呼叫：直接將指定任務視為完成。

    Args:
        bot (commands.Bot): "Natalie(...)"
        user_id (str | int): "410847926236086272"
        quest_id (str): "blackjack"
    """
    cog = bot.get_cog("Quest")
    if cog is None: return
    try:
        await cog.complete_quest(str(user_id), quest_id)
    except Exception as error:
        print(f"quest complete_quest failed: {type(error).__name__}: {error}")


class Quest(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.bot = client
        self.lobby_text_channel_id = 419108485435883533
        self.game_voice_channel_ids = [
            419108485435883535, #一般頻道1
            456422626567389206, #一般頻道2
            616238868164771861, #一般頻道3
            540856580325769226, #其他遊戲區1
            540856651805360148, #其他遊戲區2
            540856695992221706, #其他遊戲區3
        ]
        self.super_vip_min_marshmallow = 50
        self.leaderboard_limit = 10
        self.settlement_hour = 6
        self.settlement_minute = 0
        self.invite_cache = {}
        self.quests = [
            LobbyChat3Quest(self.lobby_text_channel_id),
            LobbyChat10Quest(self.lobby_text_channel_id),
            Voice30MinQuest(),
            Voice2HourQuest(),
            Voice5HourQuest(),
            VoiceStream1HourQuest(),
            InviteMemberQuest(),
            BlackjackQuest(),
            SquidRpsHardWinQuest(),
        ]
        self.quest_map = {quest.quest_id: quest for quest in self.quests}
        self.daily_settlement.start()
        self.voice_quest_record.start()

    async def cog_load(self):
        """
        Cog 載入後若機器人已就緒，立刻同步邀請快取。
        """
        if self.bot.is_ready():
            await self.refresh_invite_cache()

    async def cog_unload(self):
        """
        卸載時停止排程。
        """
        self.daily_settlement.cancel()
        self.voice_quest_record.cancel()

    def get_quest(self, quest_id: str) -> DailyQuest | None:
        """
        依任務 ID 取得任務模組。

        Args:
            quest_id (str): "blackjack"

        Returns:
            quest (DailyQuest | None): "BlackjackQuest()"
        """
        return self.quest_map.get(quest_id)

    def super_vip_sort_key(self, user_document: dict) -> tuple:
        """
        至寶結算比較鍵：棉花糖、等級、蛋糕、Discord user id，皆由大到小。

        Args:
            user_document (dict): "{'_id': '4108', 'marshmallow': 52, 'level': 10, 'cake': 100}"

        Returns:
            sort_key (tuple): "(52, 10, 100, 4108)"
        """
        return (
            int(user_document.get("marshmallow", 0)),
            int(user_document.get("level", 1)),
            int(user_document.get("cake", 0)),
            int(user_document.get("_id", 0)),
        )

    def resolve_display_name(self, guild: discord.Guild | None, user_id: str) -> str:
        """
        解析顯示名稱，找不到則回傳 user id。

        Args:
            guild (discord.Guild | None): "Guild(...)"
            user_id (str): "410847926236086272"

        Returns:
            display_name (str): "AAA"
        """
        if guild is not None:
            member = guild.get_member(int(user_id))
            if member is not None: return member.display_name
        user = self.bot.get_user(int(user_id))
        if user is not None: return user.display_name
        return user_id

    async def report_event(self, user_id: str, event_type: str, amount: int = 1):
        """
        依事件類型推進所有符合的每日任務。

        Args:
            user_id (str): "410847926236086272"
            event_type (str): "lobby_chat"
            amount (int): "1"
        """
        if amount <= 0: return
        for quest in self.quests:
            if not quest.matches_event(event_type): continue
            await self.add_progress(user_id, quest, amount)

    async def complete_quest(self, user_id: str, quest_id: str):
        """
        直接將指定任務推進至完成門檻。

        Args:
            user_id (str): "410847926236086272"
            quest_id (str): "blackjack"
        """
        quest = self.get_quest(quest_id)
        if quest is None: return
        await self.add_progress(user_id, quest, quest.target)

    async def add_progress(self, user_id: str, quest: DailyQuest, amount: int = 1):
        """
        增加任務進度，達標則立即發放獎勵。

        Args:
            user_id (str): "410847926236086272"
            quest (DailyQuest): "LobbyChat3Quest(...)"
            amount (int): "1"
        """
        if amount <= 0: return
        await common.mongo_storage.ensure_user_document(user_id)
        collection = common.mongo_storage.get_collection("userdata")
        progress_field = f"quest_daily.{quest.quest_id}.progress"
        updated = await collection.find_one_and_update(
            {"_id": user_id, f"quest_daily.{quest.quest_id}.completed": {"$ne": True}},
            {"$inc": {progress_field: amount}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None: return
        quest_state = updated.get("quest_daily", {}).get(quest.quest_id, {})
        progress = int(quest_state.get("progress", 0))
        if progress < quest.target: return
        await self.award_quest(user_id, quest)

    async def award_quest(self, user_id: str, quest: DailyQuest):
        """
        將任務標記完成並發放蛋糕與棉花糖（僅發放一次）。

        Args:
            user_id (str): "410847926236086272"
            quest (DailyQuest): "BlackjackQuest()"
        """
        collection = common.mongo_storage.get_collection("userdata")
        await collection.find_one_and_update(
            {"_id": user_id, f"quest_daily.{quest.quest_id}.completed": {"$ne": True}},
            {
                "$set": {
                    f"quest_daily.{quest.quest_id}.completed": True,
                    "quest_any_completed_today": True,
                },
                "$inc": {
                    "cake": quest.cake_reward,
                    "marshmallow": quest.marshmallow_reward,
                },
            },
        )

    async def refresh_invite_cache(self):
        """
        重新讀取妹妹群目前的邀請使用次數。
        """
        guild = self.bot.get_guild(common.fake_sister_server_id)
        if guild is None: return
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            return
        cache = {}
        for invite in invites:
            inviter_id = invite.inviter.id if invite.inviter else None
            cache[invite.code] = {"uses": invite.uses, "inviter_id": inviter_id}
        self.invite_cache = cache

    async def find_used_inviter_id(self, guild: discord.Guild) -> int | None:
        """
        比對邀請快取，找出這次加入所使用的邀請人。

        Args:
            guild (discord.Guild): "Guild(...)"

        Returns:
            inviter_id (int | None): "410847926236086272"
        """
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            return None
        new_cache = {}
        used_inviter_id = None
        for invite in invites:
            inviter_id = invite.inviter.id if invite.inviter else None
            new_cache[invite.code] = {"uses": invite.uses, "inviter_id": inviter_id}
            old_entry = self.invite_cache.get(invite.code)
            old_uses = old_entry["uses"] if isinstance(old_entry, dict) else 0
            if invite.uses > old_uses and used_inviter_id is None:
                used_inviter_id = inviter_id
        if used_inviter_id is None:
            for code, old_entry in self.invite_cache.items():
                if code in new_cache: continue
                if not isinstance(old_entry, dict): continue
                used_inviter_id = old_entry.get("inviter_id")
                break
        self.invite_cache = new_cache
        return used_inviter_id

    @app_commands.command(name="quest", description="查看每日任務")
    async def quest(self, interaction: discord.Interaction):
        userid = str(interaction.user.id)
        user_data = await common.mongo_storage.ensure_user_document(userid)
        marshmallow = int(user_data.get("marshmallow", 0))
        quest_daily = user_data.get("quest_daily", {})
        if not isinstance(quest_daily, dict):
            quest_daily = {}

        embed = Embed(
            title="每日任務",
            description=(
                "透過完成每日任務，獲取棉花糖跟蛋糕!\n"
                "試著成為棉花糖數量最多的人，領取稱號獎勵吧!\n"
                "※每日任務在早上6:00刷新\n"
                "※刷新時如果每日任務未達成任何一項，棉花糖會歸0"
            ),
            color=common.bot_color,
        )
        embed.add_field(name="你的棉花糖", value=str(marshmallow), inline=False)

        for quest in self.quests:
            quest_state = quest_daily.get(quest.quest_id, {})
            if not isinstance(quest_state, dict):
                quest_state = {}
            completed = bool(quest_state.get("completed"))
            progress = int(quest_state.get("progress", 0))
            if progress > quest.target:
                progress = quest.target
            status_icon = "✅ " if completed else ""
            progress_text = "已完成" if completed else f"進度：{progress}/{quest.target}"
            embed.add_field(
                name=f"{status_icon}{quest.description}",
                value=f"獎勵：{quest.cake_reward} {common.cake_emoji}　棉花糖 x{quest.marshmallow_reward}\n{progress_text}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        """
        機器人就緒時同步邀請快取。
        """
        await self.refresh_invite_cache()

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        """
        新邀請建立時寫入快取。

        Args:
            invite (discord.Invite): "Invite(...)"
        """
        if invite.guild is None or invite.guild.id != common.fake_sister_server_id: return
        inviter_id = invite.inviter.id if invite.inviter else None
        self.invite_cache[invite.code] = {"uses": invite.uses, "inviter_id": inviter_id}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        大廳發言時推進聊天任務。

        Args:
            message (discord.Message): "Message(...)"
        """
        if message.author.bot: return
        if message.guild is None or message.guild.id != common.fake_sister_server_id: return
        if message.channel.id != self.lobby_text_channel_id: return
        await self.report_event(str(message.author.id), "lobby_chat")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        有人加入妹妹群時，嘗試把邀請任務記給邀請人。

        Args:
            member (discord.Member): "Member(...)"
        """
        if member.bot: return
        if member.guild.id != common.fake_sister_server_id: return
        inviter_id = await self.find_used_inviter_id(member.guild)
        if inviter_id is None: return
        if inviter_id == member.id: return
        await self.report_event(str(inviter_id), "invite_member")

    @tasks.loop(minutes=1)
    async def voice_quest_record(self):
        """
        每分鐘為待在遊戲區語音房的成員累加語音任務進度，直播中則另外累加直播任務。
        """
        for channel_id in self.game_voice_channel_ids:
            channel = self.bot.get_channel(channel_id)
            if channel is None: continue
            for member in channel.members:
                if member.bot: continue
                await self.report_event(str(member.id), "game_voice")
                if member.voice and member.voice.self_stream:
                    await self.report_event(str(member.id), "game_voice_stream")

    @tasks.loop(minutes=1)
    async def daily_settlement(self):
        """
        每天早上 6:00 結算棉花糖、至寶稱號，並輸出前 10 名 log。
        """
        nowtime = datetime.now(timezone(timedelta(hours=8)))
        if nowtime.hour != self.settlement_hour or nowtime.minute != self.settlement_minute: return
        today = nowtime.strftime("%Y-%m-%d")
        global_document = await common.mongo_storage.get_global_document()
        if global_document.get("quest_last_settlement_date") == today: return
        await self.settle_daily_quests()
        await common.mongo_storage.update_global_fields({"quest_last_settlement_date": today})

    async def settle_daily_quests(self):
        """
        執行每日結算：清空未做任務者的棉花糖、更新至寶、寫入管理員日誌、刷新任務進度。
        """
        userdata_collection = common.mongo_storage.get_collection("userdata")
        await userdata_collection.update_many(
            {
                "_id": {"$ne": "global"},
                "marshmallow": {"$gt": 0},
                "quest_any_completed_today": {"$ne": True},
            },
            {"$set": {"marshmallow": 0}},
        )

        ranked_users = []
        async for document in userdata_collection.find(
            {"_id": {"$ne": "global"}, "marshmallow": {"$gt": 0}},
            {"_id": 1, "marshmallow": 1, "level": 1, "cake": 1},
        ):
            document_id = document.get("_id")
            if not isinstance(document_id, str) or not document_id.isdigit(): continue
            ranked_users.append(document)
        ranked_users.sort(key=self.super_vip_sort_key, reverse=True)

        winner_id = None
        for user_document in ranked_users:
            if int(user_document.get("marshmallow", 0)) < self.super_vip_min_marshmallow: continue
            winner_id = str(user_document.get("_id"))
            break

        guild = self.bot.get_guild(common.fake_sister_server_id)
        if guild is not None:
            super_vip_role = guild.get_role(common.super_vip_id)
            if super_vip_role is not None:
                for holder in list(super_vip_role.members):
                    if winner_id is not None and str(holder.id) == winner_id: continue
                    try:
                        await holder.remove_roles(super_vip_role, reason="每日任務結算：至寶稱號更新")
                    except discord.HTTPException:
                        pass
                if winner_id is not None:
                    winner_member = guild.get_member(int(winner_id))
                    if winner_member is not None and super_vip_role not in winner_member.roles:
                        try:
                            await winner_member.add_roles(super_vip_role, reason="每日任務結算：棉花糖最多")
                        except discord.HTTPException:
                            pass

        log_lines = []
        for index, user_document in enumerate(ranked_users[:self.leaderboard_limit], start=1):
            user_id = str(user_document.get("_id"))
            marshmallow = int(user_document.get("marshmallow", 0))
            display_name = self.resolve_display_name(guild, user_id)
            suffix = " (目前至寶)" if winner_id is not None and user_id == winner_id else ""
            log_lines.append(f"{index}.{display_name} - {marshmallow}{suffix}")
        log_text = "\n".join(log_lines) if log_lines else "目前沒有人持有棉花糖"
        mod_channel = self.bot.get_channel(common.mod_log_channel)
        if mod_channel is not None:
            await mod_channel.send(embed=Embed(title="每日任務結算", description=log_text, color=common.bot_color))

        await userdata_collection.update_many(
            {"_id": {"$ne": "global"}},
            {"$unset": {"quest_daily": "", "quest_any_completed_today": ""}},
        )

    @daily_settlement.before_loop
    @voice_quest_record.before_loop
    async def event_before_loop(self):
        await self.bot.wait_until_ready()
        await self.refresh_invite_cache()


async def setup(client: commands.Bot):
    await client.add_cog(Quest(client))
