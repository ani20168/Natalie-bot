import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from . import game
import json
import time
import random
import os
import aiohttp
import asyncio
import traceback
from datetime import datetime,timezone,timedelta




class Startup(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.userdata_initialization.start()
        self.give_cake_in_vc.start()
        self.mine_mininglimit_reflash.start()
        self.voice_active_record.start()
        self.mining_machine_work.start()
        self.auto_backup_database.start()
        self.check_asf.start()

    #卸載cog時觸發
    async def cog_unload(self):
        self.userdata_initialization.cancel()
        self.give_cake_in_vc.cancel()
        self.mine_mininglimit_reflash.cancel()
        self.voice_active_record.cancel()
        self.mining_machine_work.cancel()
        self.auto_backup_database.cancel()
        self.check_asf.cancel()


    #挖礦遊戲-刷新礦場總挖礦次數
    @tasks.loop(minutes=1)
    async def mine_mininglimit_reflash(self):
        try:
            nowtime = datetime.now(timezone(timedelta(hours=8)))
            if nowtime.hour == 0 and nowtime.minute == 0:
                mining_collection = common.mongo_storage.get_collection("mining")
                global_document = await mining_collection.find_one({"_id": "global"}, {"mine_mininglimit": 1})
                if not isinstance(global_document, dict): return
                mine_mininglimit = global_document.get("mine_mininglimit", {})
                if not isinstance(mine_mininglimit, dict): return
                reset_mininglimit = {key: 500 for key in mine_mininglimit.keys()}
                await mining_collection.update_one({"_id": "global"}, {"$set": {"mine_mininglimit": reset_mininglimit}}, upsert=True)
        except Exception:
            traceback.print_exc()

    #挖礦遊戲-自動挖礦機的挖礦流程
    @tasks.loop(minutes=1)
    async def mining_machine_work(self):
        try:
            nowtime = datetime.now(timezone(timedelta(hours=8)))
            if nowtime.hour % 3 != 0 or nowtime.minute != 0: return

            # 只掃描有啟用礦機的玩家文件；礦場次數改以原子 $inc 扣減，避免與手動挖礦互相覆蓋。
            mining_collection = common.mongo_storage.get_collection("mining")
            mining_game = game.MiningGame(self.bot)
            machine_users_cursor = mining_collection.find({"_id": {"$ne": "global"}, "machine_amount": {"$gte": 1}, "machine_mine": {"$exists": True}})
            async for user_document in machine_users_cursor:
                userid = str(user_document.get("_id"))
                machine_amount = int(user_document.get("machine_amount", 0))
                machine_mine = user_document.get("machine_mine")
                if machine_amount < 1 or not machine_mine: continue
                reward_probabilities = mining_game.mineral_chancelist.get(machine_mine)
                if not isinstance(reward_probabilities, dict): continue

                # 累積本位玩家本輪抽到的礦物，最後一次 $inc 更新，減少 DB 寫入次數。
                rewards_increment_map = {}
                target_key = f"mine_mininglimit.{machine_mine}"
                for _ in range(machine_amount):
                    # 與手動挖礦相同：條件式原子扣減，額度用盡則提前結束該玩家流程。
                    remain_document = await mining_collection.find_one_and_update(
                        {"_id": "global", target_key: {"$gt": 0}},
                        {"$inc": {target_key: -1}},
                        return_document=common.ReturnDocument.AFTER,
                    )
                    if remain_document is None: break

                    # 依礦場機率表抽一次獎；抽到「石頭」視為沒有需要入庫的獎勵。
                    random_num = random.random()
                    current_probability = 0
                    for reward, probability in reward_probabilities.items():
                        current_probability += probability
                        if random_num < current_probability:
                            if reward != "石頭":
                                rewards_increment_map[reward] = rewards_increment_map.get(reward, 0) + 1
                            break

                if rewards_increment_map:
                    await mining_collection.update_one({"_id": userid}, {"$inc": rewards_increment_map}, upsert=True)
        except Exception:
            traceback.print_exc()


    @tasks.loop(seconds=5, count=1)
    async def check_asf(self):
        """
        開機後測試 ASF API 連線（僅 PRD 環境執行一次）。

        Args:
          無參數 (None): "None"

        Returns:
          (None): "None"
        """
        try:
            if common.mongo_storage.get_runtime_env() != "PRD": return
            admin_channel = self.bot.get_channel(common.admin_log_channel)
            if admin_channel is None: return
            api_headers = {
                "accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.4044.138 Safari/537.36",
            }
            error_message = None
            version_text = ""
            try:
                async with self.bot.session.post(
                    common.asf_api_url,
                    json={"Command": "version"},
                    headers=api_headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response_text = await response.text()
                    if response.status != 200:
                        error_message = f"HTTP {response.status}: {response_text[:200]}"
                    else:
                        try:
                            data = json.loads(response_text)
                        except json.JSONDecodeError:
                            error_message = f"回應格式錯誤: {response_text[:200]}"
                        else:
                            if not data.get("Success", False):
                                error_message = str(data.get("Result", response_text) or "ASF 回傳失敗")
                            else:
                                version_text = str(data.get("Result", ""))
            except asyncio.TimeoutError:
                error_message = "連線逾時"
            except aiohttp.ClientError as error:
                error_message = str(error)
            except Exception as error:
                error_message = f"{type(error).__name__}: {error}"
            if error_message is None:
                embed = Embed(title="ASF 連線測試", description=f"已連線。 (版本:{version_text})", color=common.bot_color)
            else:
                embed = Embed(title="ASF 連線測試", description=error_message, color=common.bot_error_color)
            await admin_channel.send(embed=embed)
        except Exception:
            traceback.print_exc()

    #用戶資料初始化/檢查
    @tasks.loop(seconds=5,count=1)
    async def userdata_initialization(self):
        try:
            userdata_collection = common.mongo_storage.get_collection("userdata")
            defaults = common.mongo_storage.get_user_defaults()
            defaults_without_blackjack = {key: value for key, value in defaults.items() if key != "blackjack_playing"}
            for member in self.bot.get_all_members():
                userid = str(member.id)
                await userdata_collection.update_one(
                    {"_id": userid},
                    {
                        "$setOnInsert": defaults_without_blackjack,
                        "$set": {"blackjack_playing": False},
                        "$unset": {"afk_start": ""},
                    },
                    upsert=True,
                )
        except Exception:
            traceback.print_exc()

    #每5分鐘，有在指定的語音頻道內則給予蛋糕
    @tasks.loop(minutes=5)
    async def give_cake_in_vc(self):
        try:
            vclist = [
                419108485435883535,
                456422626567389206,
                616238868164771861,
                540856580325769226,
                540856651805360148,
                540856695992221706,
                540484453445664768
            ]

            reward_map = {}
            for channelid in vclist:
                channel = self.bot.get_channel(channelid)
                if channel is None: continue
                for member in channel.members:
                    if member.bot: continue
                    reward = 3  # 在語音房的基礎獎勵
                    # VIP、MOD、ADMIN 額外獎勵
                    if any(role.id in [419185180134080513, common.vip_role_id, 419185995078959104] for role in member.roles):
                        reward += 3
                    # 直播額外獎勵
                    if member.voice and member.voice.self_stream:
                        reward += 10
                    # 至寶額外獎勵
                    if any(role.id == common.super_vip_id for role in member.roles):
                        reward += 15
                    if reward <= 0: continue
                    member_id = str(member.id)
                    reward_map[member_id] = reward_map.get(member_id, 0) + reward

            userdata_collection = common.mongo_storage.get_collection("userdata")
            defaults = common.mongo_storage.get_user_defaults()
            for member_id, reward in reward_map.items():
                await userdata_collection.update_one({"_id": member_id}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": reward}}, upsert=True)
        except Exception:
            traceback.print_exc()

    #紀錄會員在語音內的分鐘數，並給予前三名獎勵
    @tasks.loop(minutes=1)
    async def voice_active_record(self):
        try:
            vclist = [
                419108485435883535,
                456422626567389206,
                616238868164771861,
                540856580325769226,
                540856651805360148,
                540856695992221706,
                540484453445664768
            ]

            for channelid in vclist:
                channel = self.bot.get_channel(channelid)
                if channel is None: continue
                for member in channel.members:
                    userid = str(member.id)
                    userdata_collection = common.mongo_storage.get_collection("userdata")
                    defaults = common.mongo_storage.get_user_defaults()
                    await userdata_collection.update_one({"_id": userid}, {"$setOnInsert": defaults, "$inc": {"voice_active_minutes": 1}}, upsert=True)

                    # 是否再掛機?(語音房內只有1人、靜音狀態)
                    member_data = await common.mongo_storage.get_user(userid)
                    if len(channel.members) == 1 and member.voice and member.voice.self_mute == True:
                        afk_start = int(member_data.get("afk_start", 0)) if isinstance(member_data, dict) else 0
                        if afk_start == 0:
                            await common.mongo_storage.update_user_fields(userid, {"afk_start": int(time.time())})
                        else:
                            elapsed_time = int(time.time()) - afk_start
                            if elapsed_time >= 20 * 60:
                                afk_role = member.guild.get_role(577690189942751252)
                                if afk_role not in member.roles:
                                    await member.add_roles(afk_role,reason="掛機持續20分鐘，添加身分組。")
                    else:
                        if isinstance(member_data, dict) and "afk_start" in member_data:
                            await common.mongo_storage.unset_user_fields(userid, ["afk_start"])

            #每日結算
            nowtime = datetime.now(timezone(timedelta(hours=8)))
            if nowtime.hour == 0 and nowtime.minute == 0:
                userdata_collection = common.mongo_storage.get_collection("userdata")
                sorted_data = []
                async for document in userdata_collection.find({"_id": {"$ne": "global"}, "voice_active_minutes": {"$gt": 10}}).sort("voice_active_minutes", -1).limit(3):
                    sorted_data.append((str(document.get("_id")), document))
                base_rewards = (1200, 750, 400)
                leaderboard_lines = []
                for i, (userid, userdata) in enumerate(sorted_data[:3]):
                    user = self.bot.get_user(int(userid))
                    minutes = userdata['voice_active_minutes']
                    multiplier = 3 if minutes >= 300 else (2 if minutes >= 180 else 1)
                    reward = base_rewards[i] * multiplier
                    defaults = common.mongo_storage.get_user_defaults()
                    await userdata_collection.update_one({"_id": userid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": reward}}, upsert=True)
                    bonus_note = f"，{multiplier}倍" if multiplier > 1 else ""
                    username = user.display_name if user else userid
                    leaderboard_lines.append(f"{i + 1}.{username} 語音分鐘數:**{minutes}** (獲得{reward}塊蛋糕{bonus_note})")

                await common.mongo_storage.update_global_fields({"yesterday_voice_leaderboard": "\n".join(leaderboard_lines)})
                await userdata_collection.update_many({"_id": {"$ne": "global"}, "voice_active_minutes": {"$exists": True}}, {"$set": {"voice_active_minutes": 0}})
        except Exception:
            traceback.print_exc()

    @tasks.loop(hours=1)
    async def auto_backup_database(self):
        """
        每小時自動備份一次資料庫，並覆蓋同一份檔案。

        Args:
          無參數 (None): "None"

        Returns:
          (None): "None"
        """
        try:
            if not common.mongo_storage.get_mongo_uri(): return
            backup_dir = "data/backup"
            backup_path = os.path.join(backup_dir, "discord_latest.tar.gz")
            latest_path_file = os.path.join(backup_dir, "latest_backup.txt")
            os.makedirs(backup_dir, exist_ok=True)

            try:
                await common.mongo_storage.export_database_backup(backup_path)
                with open(latest_path_file, "w", encoding="utf-8") as file:
                    file.write(f"{backup_path}\n")
            except Exception as error:
                admin_channel = self.bot.get_channel(common.admin_log_channel)
                if admin_channel is None: return
                await admin_channel.send(embed=Embed(title="自動備份失敗", description=f"{type(error).__name__}: {error}", color=common.bot_error_color))
        except Exception:
            traceback.print_exc()

    @check_asf.before_loop
    @userdata_initialization.before_loop    
    @give_cake_in_vc.before_loop
    @mine_mininglimit_reflash.before_loop
    @voice_active_record.before_loop
    @mining_machine_work.before_loop
    @auto_backup_database.before_loop
    async def event_before_loop(self):
        await self.bot.wait_until_ready()
        
class AfkDisconnect(commands.Cog):
    def __init__(self, bot: commands.Bot):
        """初始化 Cog 與相關狀態。
        Args:
            bot (commands.Bot): Discord Bot 實例
        Returns:
            None
        """
        self.bot = bot
        self.whitelist = [
            # "410847926236086272", #ANI
            "587934995063111681", #xu6
            "823967449149603861" #小八
        ]
        self.server_id = common.fake_sister_server_id
        self.lobby_textchannel_id = 419108485435883533
        self._afk_state = {}
        self.afk_disconnect_event.start()

    #卸載cog時觸發
    async def cog_unload(self):
        self.afk_disconnect_event.cancel()

    @tasks.loop(minutes=1)
    async def afk_disconnect_event(self) -> None:
        """每分鐘檢查白名單用戶是否符合 AFK 斷線條件並執行語音斷線。
        Args:
            self (AfkDisconnect): Cog 自身
        Returns:
            None
        """
        try:
            guild = self.bot.get_guild(self.server_id)
            if guild is None:
                return
            for uid in self.whitelist:
                member = guild.get_member(int(uid))
                if member is None:
                    continue
                voice_state = member.voice
                state = self._afk_state.setdefault(uid, {"counter": 0, "last_channel": None})
                trigger = 15
                user_data = await common.mongo_storage.get_user(uid)
                if isinstance(user_data, dict):
                    trigger = int(user_data.get("afkdisconnect_trigger", 15))
                if voice_state is None:
                    state["counter"] = 0
                    state["last_channel"] = None
                    continue
                if state["last_channel"] != voice_state.channel.id:
                    state["counter"] = 0
                    state["last_channel"] = voice_state.channel.id
                elif voice_state.self_mute or voice_state.mute:
                    state["counter"] += 1
                    if state["counter"] >= trigger:
                        await member.move_to(None, reason=f"掛機已持續{trigger}分鐘，觸發自動斷連!")
                        state["counter"] = 0
                        state["last_channel"] = None
                else:
                    state["counter"] = 0
        except Exception:
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """白名單成員在大廳文字頻道發言時重置掛機計時。
        Args:
            message (discord.Message): 收到的訊息物件
        Returns:
            None
        """
        if message.author.bot:
            return
        if message.channel.id == self.lobby_textchannel_id and str(message.author.id) in self.whitelist:
            state = self._afk_state.get(str(message.author.id))
            if state:
                state["counter"] = 0

    @afk_disconnect_event.before_loop
    async def event_before_loop(self):
        await self.bot.wait_until_ready()


async def setup(client:commands.Bot):
    await client.add_cog(AfkDisconnect(client))
    await client.add_cog(Startup(client))