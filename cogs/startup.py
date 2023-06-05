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
        self.clearstardoor.start()  
        self.userdata_initialization.start()
        self.give_cake_in_vc.start()
        self.mine_mininglimit_reflash.start()
        self.voice_active_record.start()
        self.mining_machine_work.start()

    #卸載cog時觸發
    async def cog_unload(self):
        self.clearstardoor.cancel()
        self.userdata_initialization.cancel()
        self.give_cake_in_vc.cancel()
        self.mine_mininglimit_reflash.cancel()
        self.voice_active_record.cancel()
        self.mining_machine_work.cancel()

        
    #自動鎖定過期的星門
    @tasks.loop(hours=1)
    async def clearstardoor(self):
        nowtime = datetime.now(timezone(timedelta(hours=8)))
        if nowtime.hour == 0:
            list = self.bot.get_channel(1057894690478899330).threads           
            if len(list) != 0:
                for thread in list:
                    if any( tag.name == "星門" for tag in thread.applied_tags):
                        await thread.edit(archived=True,locked=True,reason="自動鎖定過期的星門")

    #挖礦遊戲-刷新礦場總挖礦次數
    @tasks.loop(minutes=1)
    async def mine_mininglimit_reflash(self):
        nowtime = datetime.now(timezone(timedelta(hours=8)))
        if nowtime.hour == 0 and nowtime.minute == 0:
            async with common.jsonio_lock:
                data = common.dataload("data/mining.json")
                for key, value in data["mine_mininglimit"].items():
                    if value != 500:
                        data["mine_mininglimit"][key] = 500
                common.datawrite(data,"data/mining.json")

    #挖礦遊戲-自動挖礦機的挖礦流程
    @tasks.loop(hours=3)
    async def mining_machine_work(self):
        async with common.jsonio_lock:
            data = common.dataload("data/mining.json")
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
            common.datawrite(data,"data/mining.json")
            

    #用戶資料初始化/檢查
    @tasks.loop(seconds=5,count=1)
    async def userdata_initialization(self):
        async with common.jsonio_lock:
            data = common.dataload()

            for member in self.bot.get_all_members():
                if str(member.id) not in data:
                    data[str(member.id)] = {"cake": 0}
                data[str(member.id)]["blackjack_playing"] = False
                if 'afk_start' in data[str(member.id)]:
                    del data[str(member.id)]['afk_start']
            
            common.datawrite(data)

    #每5分鐘，有在指定的語音頻道內則給予蛋糕
    @tasks.loop(minutes=5)
    async def give_cake_in_vc(self):
        vclist = [
            419108485435883535,
            456422626567389206,
            616238868164771861,
            540856580325769226,
            540856651805360148,
            540856695992221706]
        
        async with common.jsonio_lock:
            data = common.dataload()

            for channelid in vclist:
                channel = self.bot.get_channel(channelid)
                for member in channel.members:
                    #如果資料內有用戶ID(正常都會有)，並且非機器人
                    if str(member.id) in data and member.bot == False:
                        data[str(member.id)]["cake"] += 1
                    #VIP、MOD、ADMIN獎勵
                    if str(member.id) in data and any(role.id in [419185180134080513,605730134531637249,419185995078959104] for role in member.roles):
                        data[str(member.id)]["cake"] += 1
                    #直播獎勵
                    if str(member.id) in data and member.voice.self_stream == True:
                        data[str(member.id)]["cake"] += 2
                            
            common.datawrite(data)

    #紀錄會員在語音內的分鐘數，並給予前三名獎勵
    @tasks.loop(minutes=1)
    async def voice_active_record(self):
        vclist = [
            419108485435883535,
            456422626567389206,
            616238868164771861,
            540856580325769226,
            540856651805360148,
            540856695992221706]
        
        async with common.jsonio_lock:
            data = common.dataload()
            for channelid in vclist:
                channel = self.bot.get_channel(channelid)
                for member in channel.members:
                    userid = str(member.id)
                    if userid in data:
                        #語音活躍分鐘數+1
                        if "voice_active_minutes" not in data[userid]:
                            data[userid]['voice_active_minutes'] = 0
                        data[userid]['voice_active_minutes'] += 1

                        # 是否再掛機?(語音房內只有1人、靜音狀態)
                        if len(channel.members) == 1 and member.voice.self_mute == True:
                            # 如果資料中不存在該成員的AFK時間，則添加
                            if 'afk_start' not in data[userid]:
                                data[userid]['afk_start'] = int(time.time())
                            else:
                                # 檢查是否超過20分鐘
                                elapsed_time = int(time.time()) - data[userid]['afk_start']
                                if elapsed_time >= 20 * 60:
                                    # 如果超過20分鐘，給予AFK角色
                                    afk_role = member.guild.get_role(577690189942751252)
                                    if afk_role not in member.roles:
                                        await member.add_roles(afk_role,reason="掛機持續20分鐘，添加身分組。")
                        else:
                            # 如果用戶不再AFK狀態，清除計時
                            if 'afk_start' in data[userid]:
                                del data[userid]['afk_start']

            
            #每日結算
            nowtime = datetime.now(timezone(timedelta(hours=8)))
            if nowtime.hour == 0 and nowtime.minute == 0:
                #如果用戶資料內有voice_active_minutes且>10分鐘
                sorted_data = sorted([(userid, userdata) for userid, userdata in data.items() if isinstance(userdata, dict) and 'voice_active_minutes' in userdata and userdata['voice_active_minutes'] > 10], key=lambda x: x[1]['voice_active_minutes'], reverse=True)
                #列出前三名，並給予獎勵
                data['yesterday_voice_leaderboard'] = ""
                for i, (userid, userdata) in enumerate(sorted_data[:3]):
                    user = self.bot.get_user(int(userid))
                    if i == 0:
                        data[userid]['cake'] += 300
                        data['yesterday_voice_leaderboard'] += f"{i + 1}.{user.name} 語音分鐘數:**{userdata['voice_active_minutes']}** (獲得300塊蛋糕)\n"
                    elif i == 1:
                        data[userid]['cake'] += 200
                        data['yesterday_voice_leaderboard'] += f"{i + 1}.{user.name} 語音分鐘數:**{userdata['voice_active_minutes']}** (獲得200塊蛋糕)\n"
                    elif i == 2:
                        data[userid]['cake'] += 100
                        data['yesterday_voice_leaderboard'] += f"{i + 1}.{user.name} 語音分鐘數:**{userdata['voice_active_minutes']}** (獲得100塊蛋糕)"
                #隔日重置        
                for userid, userdata in data.items():
                    if isinstance(userdata, dict) and 'voice_active_minutes' in userdata:
                        data[userid]['voice_active_minutes'] = 0
            common.datawrite(data)

    @userdata_initialization.before_loop 
    @clearstardoor.before_loop    
    @give_cake_in_vc.before_loop
    @mine_mininglimit_reflash.before_loop
    @voice_active_record.before_loop
    @mining_machine_work.before_loop
    async def event_before_loop(self):
        await self.bot.wait_until_ready()
        

async def setup(client:commands.Bot):
    await client.add_cog(Startup(client))