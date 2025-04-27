import json
import asyncio

#這裡放置常用的資料
bot_color = 0x00DFEB                     #embed顏色
bot_error_color = 0xFF5151               #出現錯誤訊息的embed顏色
admin_log_channel = 543641756042788864   #admin日誌ID
mod_log_channel = 1062348474152136714    #管理員日誌ID
bot_owner_id = 410847926236086272        #我的ID
cake_emoji_id = 896670335326371840       #蛋糕ID
fake_sister_server_id = 419108485435883531

#讀寫保護鎖
jsonio_lock = asyncio.Lock()

def dataload(filepath="data/data.json") -> dict :
    with open(filepath, "r") as f:
        data = json.load(f)
    return data

def datawrite(data, filepath="data/data.json"):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)


class LevelSystem:
    def __init__(self) -> None:
        self.level = 1
        self.level_exp = 0
        self.level_next_exp = 60

    def read_info(self,memberid: str):
        data = dataload()
        if "level" in data[memberid]:
            self.level = data[memberid]["level"]
            self.level_exp = data[memberid]["level_exp"]
            self.level_next_exp = data[memberid]["level_next_exp"]
        else:
            data[memberid]["level"] = self.level
            data[memberid]["level_exp"] = self.level_exp
            data[memberid]["level_next_exp"] = self.level_next_exp
            datawrite(data)
            
        return self