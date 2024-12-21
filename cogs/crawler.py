from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
import time
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
import re




class SteamFreeGameCrawler(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.bahamut_already_parser_url = []
        self.steamgroup_already_parser_url = []
        self.headers = {
            'User-Agent':"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        self.freegame_notice_channel = self.bot.get_channel(1091267312537047040)
        self.main.start()

    #卸載cog時觸發
    async def cog_unload(self):
        self.main.cancel()

    @tasks.loop(hours=2)
    async def main(self):
        game_list = []
        bahamut_gamelist, steamgroup_gamelist = await asyncio.gather(
            self.bahamut_source(),
            self.steam_group_source()
        )
        game_list = bahamut_gamelist + steamgroup_gamelist

        unique_game_ids = set()
        unique_gamelist = []
        for url in game_list:
            game_id = self.get_game_id(url)
            if game_id and game_id not in unique_game_ids:
                unique_game_ids.add(game_id)
                unique_gamelist.append(url)

        data = common.dataload()
        for i in range(len(unique_gamelist) - 1, -1, -1):  # 从列表的最后一个元素向前迭代
            needcheck_game = unique_gamelist[i]
            game_id = self.get_game_id(needcheck_game)
            if game_id in data.get("steam_freegame_alreadypost", []):
                unique_gamelist.pop(i)  # 移除当前元素
        async with aiohttp.ClientSession() as session:
            tasks = [self.steam_check_free(session, game) for game in unique_gamelist]
            await asyncio.gather(*tasks)
        await self.freegame_notice_channel.edit(topic=f"爬蟲最後檢查時間:{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    async def web_request(self, session, url):
        try:
            async with session.get(url,headers=self.headers,timeout=10) as response:
                if response.status != 200:
                    print(f"error url:{url},status code:{response.status},time:{datetime.now().strftime('%m/%d %H:%M:%S')}")
                    return None
                return await response.text()
        except Exception as e:
            print(f"web_request get except, URL: {url},errormsg:{e},time:{datetime.now().strftime('%m/%d %H:%M:%S')}")
            return None

    async def bahamut_source(self):
        source_url = "https://forum.gamer.com.tw/B.php?bsn=60599&subbsn=10"
        async with aiohttp.ClientSession() as session:
            response = await self.web_request(session, source_url)
            if response is None: return []
            subbsn_soup = BeautifulSoup(response, "html.parser")
            article_elements = subbsn_soup.find_all(class_="b-list__row b-list-item b-imglist-item")

            tasks = [self.bahamut_article_process(session, article) for article in article_elements]
            game_lists = await asyncio.gather(*tasks)
            
            all_game_lists = [game for game_list in game_lists if game_list for game in game_list]
            return all_game_lists

    async def bahamut_article_process(self, session, article_element):
        title_element = article_element.find(class_="b-list__main__title")
        article_url = "https://forum.gamer.com.tw/" + title_element.get("href")
        if article_url not in self.bahamut_already_parser_url:
            self.bahamut_already_parser_url.append(article_url)
            response = await self.web_request(session, article_url)
            if response is None: return []
            return self.bahamut_find_steam_url(response)

    def bahamut_find_steam_url(self, response) ->list:
        """
        在巴哈文章內找Steam遊戲的連結
        """
        re_pattern = r'https://store\.steampowered\.com/app/\d+/.+?/'
        all_links = []
        article_soup = BeautifulSoup(response, "html.parser")
        content_elements = article_soup.find_all(class_="c-article__content")
        for content in content_elements:
            links = re.findall(re_pattern, str(content))
            all_links.extend(links)
        return all_links
        
    async def steam_check_free(self, session, game_url):
        response = await self.web_request(session, game_url)
        if response is None: return
        game_page_soup = BeautifulSoup(response, "html.parser")
        game_buy_block = game_page_soup.find(class_="game_area_purchase_game_wrapper")
        if game_buy_block is None: return 
        # 限時免費資訊(X月X日前可免費取得)
        free_to_keep_info = game_buy_block.find('p', class_="game_purchase_discount_quantity")
        free_to_keep_info_text = free_to_keep_info.text.strip() if free_to_keep_info else None
        if free_to_keep_info_text is None: return

        # 搜索匹配日期時間格式，支援可選年份
        # 格式範例：
        #   - 4 Jan @ 2:00am
        #   - Jan 4 @ 2:00am
        #   - 4 Jan, 2025 @ 2:00am
        #   - Jan 4, 2025 @ 2:00am
        free_date_match = re.search(
            r"(\d{1,2}\s+\w+(?:,?\s*\d{4})?\s+@\s+\d{1,2}:\d{2}(?:am|pm))|"
            r"(\w+\s+\d{1,2}(?:,?\s*\d{4})?\s+@\s+\d{1,2}:\d{2}(?:am|pm))",
            free_to_keep_info_text,
            re.IGNORECASE
        )

        if free_date_match:
            # 擷取匹配到的字串並做前置處理
            date_str = free_date_match.group(0)
            # 例如 "4 Jan, 2025 @ 2:00am" -> "4 Jan, 2025 2:00 AM"
            date_str = date_str.replace(" @ ", " ") \
                            .replace("am", " AM") \
                            .replace("pm", " PM") \
                            .replace(",", "")  # 去逗號，方便後續 datetime.strptime

            # 判斷是否含有年份
            if re.search(r"\d{4}", date_str):
                #   - 4 Jan 2025 2:00 AM  (日在前)
                #   - Jan 4 2025 2:00 AM  (月在前)
                if re.match(r"^\d{1,2}\s+\w+\s+\d{4}", date_str):
                    date_format = "%d %b %Y %I:%M %p"
                else:
                    date_format = "%b %d %Y %I:%M %p"
            else:
                # 無年份
                if re.match(r"^\d{1,2}\s+\w+", date_str):
                    date_format = "%d %b %I:%M %p"
                else:
                    date_format = "%b %d %I:%M %p"

            # 使用 Python 內建的 ZoneInfo 來處理時區(請求時，回傳的時間會是太平洋時區)
            pacific_zone = ZoneInfo("America/Los_Angeles")
            taipei_zone = ZoneInfo("Asia/Taipei")

            # 解析為 naive datetime，再指定為太平洋時間
            date_pst = datetime.strptime(date_str, date_format)
            date_pst = date_pst.replace(tzinfo=pacific_zone)

            # 轉換到台灣時區
            date_tw = date_pst.astimezone(taipei_zone)

            # 格式化輸出 (ex: "12 月 21 日 上午 02:00")
            date_tw_str = (date_tw.strftime("%m 月 %d 日 %p %I:%M")
                                .lstrip("0")      # 去除月若為0x時的 '0'
                                .replace(" 0", " ") 
                                .replace("AM", "上午")
                                .replace("PM", "下午"))
        else:
            print(f"free to keep match error! game url: {game_url} original text:{free_to_keep_info_text}")
            return

        # 折扣幅度
        discount_pct = game_buy_block.find('div', class_="discount_pct")
        discount_pct_text = discount_pct.text.strip() if discount_pct else None
        if discount_pct_text != "-100%": return

        # 最終價格
        final_price = game_buy_block.find('div', class_="discount_final_price")
        final_price_text = final_price.text.strip() if final_price else None
        await self.post_freegame(game_url, date_tw_str, discount_pct_text, final_price_text)

    async def post_freegame(self, game_url, free_info, discount_pct, final_price):
        #free_info:幾月幾號前可免費取得(日期)
        post_text = f"{game_url}\n{free_info} 前可以免費取得! ({discount_pct} {final_price})"
        await self.freegame_notice_channel.send(content=post_text)
        game_id = self.get_game_id(game_url)
        async with common.jsonio_lock:
            data = common.dataload()
            if "steam_freegame_alreadypost" not in data:
                data["steam_freegame_alreadypost"] = []
            data["steam_freegame_alreadypost"].append(game_id)
            common.datawrite(data)

    def get_game_id(self, url):
        match = re.search(r"https://store.steampowered.com/app/(\d+)", url)
        if match:
            game_id = match.group(1)
            return game_id
        else:
            return ""

    async def steam_group_source(self):
        #從群組的公告區塊找
        group_announcements_url = [
            "https://steamcommunity.com/groups/freegamesfinders/announcements",
            "https://steamcommunity.com/groups/freegamesinfoo/announcements",
            ]
        async with aiohttp.ClientSession() as session:
            tasks = [self.steam_group_find_steam_url(session, group_url) for group_url in group_announcements_url]
            game_lists = await asyncio.gather(*tasks)
            all_game_lists = [game for game_list in game_lists if game_list for game in game_list]
            for game_url in all_game_lists:
                #已經爬過的就刪掉
                if game_url in self.steamgroup_already_parser_url:
                    all_game_lists.remove(game_url)
                else:
                    self.steamgroup_already_parser_url.append(game_url)
            return all_game_lists

    async def steam_group_find_steam_url(self, session, group_url):
        response = await self.web_request(session, group_url)
        if response is None: return []
        group_announcements_soup = BeautifulSoup(response, "html.parser")
        announcements_element = group_announcements_soup.find_all(class_="announcement")
        re_pattern = r'https://store\.steampowered\.com/app/\d+(?:/.+?/)?'
        all_links = []
        for announcement in announcements_element:
            links = re.findall(re_pattern, str(announcement))
            all_links.extend(links)
        return all_links

    @main.before_loop
    async def event_before_loop(self):
        await self.bot.wait_until_ready()

async def setup(client:commands.Bot):
    await client.add_cog(SteamFreeGameCrawler(client))