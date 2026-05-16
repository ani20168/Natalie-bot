import json
import os
import re
import asyncio
from urllib.parse import urlparse

try:
    from pymongo import AsyncMongoClient, ReplaceOne, ReturnDocument  # pyright: ignore[reportMissingImports]
except Exception:
    AsyncMongoClient = None
    ReplaceOne = None
    ReturnDocument = None

#這裡放置常用的資料
bot_color = 0x00DFEB                     #embed顏色
bot_error_color = 0xFF5151               #出現錯誤訊息的embed顏色
admin_log_channel = 543641756042788864   #admin日誌ID
mod_log_channel = 1062348474152136714    #管理員日誌ID
bot_owner_id = 410847926236086272        #我的ID
cake_emoji_id = 896670335326371840       #蛋糕ID
cake_emoji = f"<:cake:{cake_emoji_id}>"  #直接顯示蛋糕emoji
fake_sister_server_id = 419108485435883531

# 搶紅包允許發佈的文字頻道 ID：大廳、機器人指令區、日誌
red_packet_allowed_channel_ids = [
    419108485435883533,  # 大廳
    545599471875260467,  # 機器人指令區
    admin_log_channel,  # 日誌
]

#讀寫保護鎖
class NoopAsyncLock:
    """
    Mongo 模式下的空鎖，保留原本語法相容性。

    Args:
      無參數 (None): "None"

    Returns:
      (NoopAsyncLock): "NoopAsyncLock()"
    """
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


jsonio_lock = NoopAsyncLock()


def read_local_json(filepath: str) -> dict:
    """
    從本地端 JSON 讀取資料。

    Args:
      filepath (str): "data/migration-source.json"

    Returns:
      (dict): "{'123': {'cake': 1}}"
    """
    with open(filepath, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data


class MongoStorage:
    def __init__(self) -> None:
        self.secret_path = "data/secret.json"
        self.client = None
        self.database = None
        self.db_name = "discord"
        self.user_id_pattern = re.compile(r"^\d+$")
        self.collection_name_map = {"userdata": "userdata", "mining": "mining", "odds": "odds"}
        self.user_global_dataset = {"userdata", "mining"}
        self.single_document_dataset = {"odds"}

    def read_secret_config(self) -> dict:
        """
        讀取 DB 連線設定檔。

        Args:
          無參數 (None): "None"

        Returns:
          (dict): "{'DB_URL': 'mongodb://...'}"
        """
        if not os.path.isfile(self.secret_path): return {}
        return read_local_json(self.secret_path)

    def get_runtime_env(self) -> str:
        """
        取得目前運行環境。

        Args:
          無參數 (None): "None"

        Returns:
          (str): "dev"
        """
        return os.getenv("BOT_ENV", "").strip().upper()

    def get_mongo_uri(self) -> str | None:
        """
        依環境回傳 Mongo 連線字串。

        Args:
          無參數 (None): "None"

        Returns:
          (str | None): "mongodb://user:pass@host:port/discord"
        """
        secret_data = self.read_secret_config()
        runtime_env = self.get_runtime_env()
        if runtime_env == "PRD": return secret_data.get("PRD_DB_URL")
        return secret_data.get("DB_URL")

    def get_database_name(self, uri: str | None = None) -> str:
        """
        從 URI 解析資料庫名稱。

        Args:
          uri (str | None): "mongodb://user:pass@host:port/discord"

        Returns:
          (str): "discord"
        """
        mongo_uri = uri or self.get_mongo_uri()
        if not mongo_uri: return "discord"
        parsed = urlparse(mongo_uri)
        db_name = parsed.path.lstrip("/")
        if not db_name: return "discord"
        if "?" in db_name: db_name = db_name.split("?", 1)[0]
        return db_name or "discord"

    def ensure_client(self):
        """
        確保 Mongo client 已建立且可連線。

        Args:
          無參數 (None): "None"

        Returns:
          (AsyncMongoClient): "AsyncMongoClient(...)"
        """
        if self.client is not None: return self.client
        if AsyncMongoClient is None:
            raise RuntimeError("尚未安裝 pymongo，請先安裝依賴。")

        mongo_uri = self.get_mongo_uri()
        if not mongo_uri:
            raise RuntimeError("找不到 Mongo 連線設定，請檢查 data/secret.json 的 DB_URL 與 PRD_DB_URL。")

        self.db_name = self.get_database_name(mongo_uri)
        self.client = AsyncMongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        self.database = self.client[self.db_name]
        return self.client

    def close_client(self):
        """
        關閉 Mongo 連線。

        Args:
          無參數 (None): "None"

        Returns:
          (None): "None"
        """
        if self.client is None: return
        self.client.close()
        self.client = None
        self.database = None

    async def ping_database(self) -> tuple[bool, float | None, str | None]:
        """
        測試 MongoDB 連線並回傳延遲。

        Args:
          無參數 (None): "None"

        Returns:
          (tuple[bool, float | None, str | None]): "(True, 15.3, None)"
        """
        try:
            self.ensure_client()
        except Exception as error:
            return False, None, str(error)

        start_time = asyncio.get_running_loop().time()
        try:
            await self.database.command("ping")
        except Exception as error:
            return False, None, str(error)
        latency_ms = (asyncio.get_running_loop().time() - start_time) * 1000
        return True, latency_ms, None

    def get_collection(self, dataset: str):
        """
        依資料集名稱取得對應 collection。

        Args:
          dataset (str): "userdata"

        Returns:
          (Collection | None): "Collection(Database(...), 'userdata')"
        """
        normalized_dataset = dataset.strip()
        collection_name = self.collection_name_map.get(normalized_dataset)
        if not collection_name:
            raise RuntimeError(f"未支援的資料集：{dataset}")
        self.ensure_client()
        return self.database[collection_name]

    def get_user_defaults(self) -> dict:
        """
        取得新使用者文件預設值。

        Args:
          無參數 (None): "None"

        Returns:
          (dict): "{'cake': 0, 'level': 1}"
        """
        return {
            "cake": 0,
            "level": 1,
            "level_exp": 0,
            "level_next_exp": 60,
            "blackjack_playing": False,
        }

    async def ensure_user_document(self, user_id: str, dataset: str = "userdata") -> dict:
        """
        確保使用者文件存在，不存在則建立。

        Args:
          user_id (str): "410847926236086272"
          dataset (str): "userdata"

        Returns:
          (dict): "{'_id': '4108', 'cake': 0}"
        """
        collection = self.get_collection(dataset)
        if collection is None: raise RuntimeError(f"找不到資料集對應 collection: {dataset}")
        defaults = self.get_user_defaults()
        if ReturnDocument is None:
            raise RuntimeError("pymongo ReturnDocument 無法使用。")
        return await collection.find_one_and_update(
            {"_id": str(user_id)},
            {"$setOnInsert": defaults},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    def is_user_document_key(self, key: str) -> bool:
        """
        判斷 key 是否為使用者 ID。

        Args:
          key (str): "410847926236086272"

        Returns:
          (bool): "True"
        """
        return bool(self.user_id_pattern.fullmatch(str(key)))

    async def load_data_from_mongo(self, dataset: str = "userdata") -> dict:
        """
        從 Mongo 讀取資料並轉回舊版 dict 結構。

        Args:
          dataset (str): "userdata"

        Returns:
          (dict): "{'123': {...}, 'gaming_time': 0}"
        """
        dataset = dataset.strip()
        collection = self.get_collection(dataset)

        if dataset in self.user_global_dataset:
            result = {}
            async for document in collection.find({}):
                document_id = str(document.get("_id"))
                payload = {key: value for key, value in document.items() if key != "_id"}
                if document_id == "global":
                    result.update(payload)
                    continue
                result[document_id] = payload
            return result

        if dataset in self.single_document_dataset:
            document = await collection.find_one({"_id": "global"})
            if not document: return {}
            if isinstance(document.get("data"), dict): return document["data"]
            return {key: value for key, value in document.items() if key != "_id"}

        raise RuntimeError(f"未支援的資料集路徑：{dataset}")

    async def write_data_to_mongo(self, data: dict, dataset: str = "userdata"):
        """
        將舊版 dict 結構寫入 Mongo。

        Args:
          data (dict): "{'123': {'cake': 1}, 'gaming_time': 0}"
          dataset (str): "userdata"

        Returns:
          (None): "None"
        """
        dataset = dataset.strip()
        collection = self.get_collection(dataset)

        if dataset in self.user_global_dataset:
            user_operations = []
            user_id_set = set()
            global_fields = {}
            for key, value in data.items():
                document_id = str(key)
                if self.is_user_document_key(document_id):
                    user_id_set.add(document_id)
                    document_body = value if isinstance(value, dict) else {"value": value}
                    user_operations.append(
                        ReplaceOne(
                            {"_id": document_id},
                            {"_id": document_id, **document_body},
                            upsert=True,
                        )
                    )
                else:
                    global_fields[key] = value

            if user_operations: await collection.bulk_write(user_operations, ordered=False)

            existing_ids = set()
            async for doc in collection.find({}, {"_id": 1}):
                if str(doc["_id"]) == "global": continue
                existing_ids.add(str(doc["_id"]))
            delete_ids = [item for item in existing_ids if item not in user_id_set]
            if delete_ids: await collection.delete_many({"_id": {"$in": delete_ids}})

            if global_fields:
                await collection.replace_one({"_id": "global"}, {"_id": "global", **global_fields}, upsert=True)
            else:
                await collection.delete_one({"_id": "global"})
            return

        if dataset in self.single_document_dataset:
            await collection.replace_one({"_id": "global"}, {"_id": "global", "data": data}, upsert=True)
            return

        raise RuntimeError(f"未支援的資料集路徑：{dataset}")

    async def get_user(self, user_id: str, dataset: str = "userdata") -> dict | None:
        """
        讀取單一使用者文件。

        Args:
          user_id (str): "410847926236086272"
          dataset (str): "userdata"

        Returns:
          (dict | None): "{'_id': '4108', 'cake': 1}"
        """
        collection = self.get_collection(dataset)
        if collection is None: return None
        return await collection.find_one({"_id": str(user_id)})

    async def upsert_user(self, user_id: str, user_data: dict, dataset: str = "userdata"):
        """
        新增或覆蓋單一使用者文件。

        Args:
          user_id (str): "410847926236086272"
          user_data (dict): "{'cake': 1, 'level': 2}"
          dataset (str): "userdata"

        Returns:
          (None): "None"
        """
        collection = self.get_collection(dataset)
        if collection is None: return
        await collection.replace_one({"_id": str(user_id)}, {"_id": str(user_id), **user_data}, upsert=True)

    async def update_user_fields(self, user_id: str, fields: dict, dataset: str = "userdata"):
        """
        更新單一使用者欄位。

        Args:
          user_id (str): "410847926236086272"
          fields (dict): "{'cake': 10}"
          dataset (str): "userdata"

        Returns:
          (None): "None"
        """
        collection = self.get_collection(dataset)
        if collection is None: return
        await collection.update_one({"_id": str(user_id)}, {"$set": fields}, upsert=True)

    async def unset_user_fields(self, user_id: str, field_names: list[str], dataset: str = "userdata"):
        """
        移除使用者文件欄位。

        Args:
          user_id (str): "410847926236086272"
          field_names (list[str]): "['afk_start']"
          dataset (str): "userdata"

        Returns:
          (None): "None"
        """
        if not field_names: return
        collection = self.get_collection(dataset)
        if collection is None: return
        unset_fields = {field_name: "" for field_name in field_names}
        await collection.update_one({"_id": str(user_id)}, {"$unset": unset_fields}, upsert=False)

    async def get_global_document(self, dataset: str = "userdata") -> dict:
        """
        讀取全域文件（_id: global）。

        Args:
          dataset (str): "userdata"

        Returns:
          (dict): "{'_id': 'global', 'gaming_time': 0}"
        """
        collection = self.get_collection(dataset)
        if collection is None: return {}
        document = await collection.find_one({"_id": "global"})
        if not document: return {}
        return document

    async def update_global_fields(self, fields: dict, dataset: str = "userdata"):
        """
        更新全域文件欄位。

        Args:
          fields (dict): "{'gaming_time': 12345}"
          dataset (str): "userdata"

        Returns:
          (None): "None"
        """
        collection = self.get_collection(dataset)
        if collection is None: return
        await collection.update_one({"_id": "global"}, {"$set": fields}, upsert=True)

    def count_user_and_global(self, data: dict) -> tuple[int, int]:
        """
        統計資料中使用者與全域鍵數量。

        Args:
          data (dict): "{'123': {...}, 'gaming_time': 1}"

        Returns:
          (tuple[int, int]): "(1, 1)"
        """
        user_count = 0
        global_count = 0
        for key in data.keys():
            if self.is_user_document_key(str(key)):
                user_count += 1
            else:
                global_count += 1
        return user_count, global_count

    async def migrate_json_to_mongo(self) -> dict:
        """
        將既有 JSON 檔遷移至 MongoDB。

        Args:
          無參數 (None): "None"

        Returns:
          (dict): "{'userdata_user_count': 100}"
        """
        userdata = read_local_json("data/data.json")
        mining = read_local_json("data/mining.json")
        odds_data = {}
        if os.path.isfile("data/odds.json"): odds_data = read_local_json("data/odds.json")

        userdata_user_count, userdata_global_count = self.count_user_and_global(userdata)
        mining_user_count, mining_global_count = self.count_user_and_global(mining)

        await self.write_data_to_mongo(userdata, "userdata")
        await self.write_data_to_mongo(mining, "mining")
        await self.write_data_to_mongo(odds_data, "odds")

        summary = {
            "database": self.db_name,
            "userdata_user_count": userdata_user_count,
            "userdata_global_count": userdata_global_count,
            "mining_user_count": mining_user_count,
            "mining_global_count": mining_global_count,
            "odds_key_count": len(odds_data.keys()),
            "global_document_id": "global",
        }
        return summary


mongo_storage = MongoStorage()


class LevelSystem:
    def __init__(self) -> None:
        self.level = 1
        self.level_exp = 0
        self.level_next_exp = 60

    async def read_info(self,memberid: str):
        member_key = str(memberid)
        user_data = await mongo_storage.get_user(member_key)
        if isinstance(user_data, dict) and "level" in user_data:
            self.level = user_data.get("level", self.level)
            self.level_exp = user_data.get("level_exp", self.level_exp)
            self.level_next_exp = user_data.get("level_next_exp", self.level_next_exp)
            return self

        await mongo_storage.update_user_fields(
            member_key,
            {
                "level": self.level,
                "level_exp": self.level_exp,
                "level_next_exp": self.level_next_exp,
            },
        )
        return self