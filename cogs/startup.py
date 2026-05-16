import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
from . import game
import time
import random
from datetime import datetime,timezone,timedelta




class Startup(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.userdata_initialization.start()
        self.give_cake_in_vc.start()
        self.mine_mininglimit_reflash.start()
        self.voice_active_record.start()
        self.mining_machine_work.start()

    #卸載cog時觸發
    async def cog_unload(self):
        self.userdata_initialization.cancel()
        self.give_cake_in_vc.cancel()
        self.mine_mininglimit_reflash.cancel()
        self.voice_active_record.cancel()
        self.mining_machine_work.cancel()


    #挖礦遊戲-刷新礦場總挖礦次數
    @tasks.loop(minutes=1)
    async def mine_mininglimit_reflash(self):
        nowtime = datetime.now(timezone(timedelta(hours=8)))
        if nowtime.hour == 0 and nowtime.minute == 0:
            async with common.jsonio_lock:
                data = await common.mongo_storage.load_data_from_mongo("mining")
                for key, value in data["mine_mininglimit"].items():
                    if value != 500:
                        data["mine_mininglimit"][key] = 500
                await common.mongo_storage.write_data_to_mongo(data,"mining")

    #挖礦遊戲-自動挖礦機的挖礦流程
    @tasks.loop(hours=3)
    async def mining_machine_work(self):
        async with common.jsonio_lock:
            data = await common.mongo_storage.load_data_from_mongo("mining")
            for userid, user_data in data.items():
                if isinstance(user_data, dict) and "machine_amount" in user_data and user_data["machine_amount"] >= 1:
                    #開始抽獎
                    reward_probabilities = game.MiningGame(self.bot).mineral_chancelist[user_data["machine_mine"]]
                    #有幾台礦機就挖幾次
                    for i in range(user_data["machine_amount"]):
                        #確認礦場是否已挖完?
                         if data['mine_mininglimit'][user_data['machine_mine']] != 0:
                            data['mine_mininglimit'][user_data['machine_mine']] -= 1
                            random_num = random.random()
                            current_probability = 0
                            for reward, probability in reward_probabilities.items():
                                current_probability += probability
                                if random_num < current_probability:
                                    #抽出礦物
                                    if reward != "石頭":
                                        if reward not in data[userid]:
                                            data[userid][reward] = 0
                                        data[userid][reward] += 1

                                    break
            await common.mongo_storage.write_data_to_mongo(data,"mining")
            

    #用戶資料初始化/檢查
    @tasks.loop(seconds=5,count=1)
    async def userdata_initialization(self):
        async with common.jsonio_lock:
            data = await common.mongo_storage.load_data_from_mongo()

            for member in self.bot.get_all_members():
                if str(member.id) not in data:
                    data[str(member.id)] = {"cake": 0}
                data[str(member.id)]["blackjack_playing"] = False
                if 'afk_start' in data[str(member.id)]:
                    del data[str(member.id)]['afk_start']
            
            await common.mongo_storage.write_data_to_mongo(data)

    #每5分鐘，有在指定的語音頻道內則給予蛋糕
    @tasks.loop(minutes=5)
    async def give_cake_in_vc(self):
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
                reward = 3
                if any(role.id in [419185180134080513,605730134531637249,419185995078959104] for role in member.roles):
                    reward += 3
                if member.voice and member.voice.self_stream:
                    reward += 10
                if reward <= 0: continue
                member_id = str(member.id)
                reward_map[member_id] = reward_map.get(member_id, 0) + reward

        userdata_collection = common.mongo_storage.get_collection("userdata")
        defaults = common.mongo_storage.get_user_defaults()
        for member_id, reward in reward_map.items():
            await userdata_collection.update_one({"_id": member_id}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": reward}}, upsert=True)

    #紀錄會員在語音內的分鐘數，並給予前三名獎勵
    @tasks.loop(minutes=1)
    async def voice_active_record(self):
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
            data = await common.mongo_storage.load_data_from_mongo()
            sorted_data = sorted([(userid, userdata) for userid, userdata in data.items() if isinstance(userdata, dict) and 'voice_active_minutes' in userdata and userdata['voice_active_minutes'] > 10], key=lambda x: x[1]['voice_active_minutes'], reverse=True)
            base_rewards = (600, 400, 200)
            leaderboard_lines = []
            for i, (userid, userdata) in enumerate(sorted_data[:3]):
                user = self.bot.get_user(int(userid))
                minutes = userdata['voice_active_minutes']
                multiplier = 3 if minutes >= 300 else (2 if minutes >= 180 else 1)
                reward = base_rewards[i] * multiplier
                userdata_collection = common.mongo_storage.get_collection("userdata")
                defaults = common.mongo_storage.get_user_defaults()
                await userdata_collection.update_one({"_id": userid}, {"$setOnInsert": {key: value for key, value in defaults.items() if key != "cake"}, "$inc": {"cake": reward}}, upsert=True)
                bonus_note = f"，{multiplier}倍" if multiplier > 1 else ""
                username = user.display_name if user else userid
                leaderboard_lines.append(f"{i + 1}.{username} 語音分鐘數:**{minutes}** (獲得{reward}塊蛋糕{bonus_note})")

            await common.mongo_storage.update_global_fields({"yesterday_voice_leaderboard": "\n".join(leaderboard_lines)})
            for userid, userdata in data.items():
                if isinstance(userdata, dict) and 'voice_active_minutes' in userdata:
                    await common.mongo_storage.update_user_fields(userid, {"voice_active_minutes": 0})

    @userdata_initialization.before_loop    
    @give_cake_in_vc.before_loop
    @mine_mininglimit_reflash.before_loop
    @voice_active_record.before_loop
    @mining_machine_work.before_loop
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
            "587934995063111681" #xu6
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
        guild = self.bot.get_guild(self.server_id)
        if guild is None:
            return
        data = await common.mongo_storage.load_data_from_mongo()
        for uid in self.whitelist:
            member = guild.get_member(int(uid))
            if member is None:
                continue
            voice_state = member.voice
            state = self._afk_state.setdefault(uid, {"counter": 0, "last_channel": None})
            trigger = data.get(uid, {}).get("afkdisconnect_trigger", 15)
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