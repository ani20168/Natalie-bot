from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
import time
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import re




class SteamFreeGameCrawler(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.bahamut_already_parser_url = []
        self.headers = {
            'User-Agent':"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        }
        self.main.start()

    #卸載cog時觸發
    async def cog_unload(self):
        self.main.cancel()

    @tasks.loop(minutes=1)
    async def main(self):
        game_list = await self.bahamut_source()
        data = common.dataload()
        for needcheck_game in game_list:
            game_id = self.get_game_id(needcheck_game)
            if game_id in data["steam_freegame_alreadypost"]:
                game_list.remove(game_id)
        async with aiohttp.ClientSession() as session:
            tasks = [self.steam_check_free(session, game) for game in game_list]
            await asyncio.gather(*tasks)

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
            if response is None: return
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
        free_date_match = re.search(r"(\d{1,2} \w+ @ \d{1,2}:\d{2}(am|pm)?)|(\w+ \d{1,2} @ \d{1,2}:\d{2}(am|pm)?)", free_to_keep_info_text)

        if free_date_match:
            # 匹配到的时间字符串
            print(free_date_match.group(0))
            date_str = free_date_match.group(0).replace(" @ ", " ")
            date_str = date_str.replace("am", " AM").replace("pm", " PM")
            # 解析时间字符串（太平洋时间）
            pst_zone = pytz.timezone('America/Los_Angeles')
            # 注意解析格式中的月份应为缩写形式，这里简化处理，具体应根据实际情况调整
            try:
                date_pst = datetime.strptime(date_str, "%b %d %I:%M %p")
            except:
                date_pst = datetime.strptime(date_str, "%d %b %I:%M %p")
            date_pst = pst_zone.localize(date_pst, is_dst=None)  # 自动处理夏令时
            # 转换到台湾时区（UTC+8）
            tw_zone = pytz.timezone('Asia/Taipei')
            date_tw = date_pst.astimezone(tw_zone)
            # 格式化输出，确保月份和日期不带前导零，同时处理前导零问题
            date_tw_str = date_tw.strftime("%m 月 %d 日 %p %I:%M").lstrip("0").replace(" 0", " ").replace("AM", "上午").replace("PM", "下午")
        else:
            print(f"free to keep match error! original text:{free_to_keep_info_text}")

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
        post_text = f"{game_url}\n{free_info}前可以免費取得! ({discount_pct} {final_price})"
        await self.bot.get_channel(common.admin_log_channel).send(content=post_text)
        game_id = self.get_game_id(game_url)
        async with common.jsonio_lock:
            data = common.dataload()
            if "steam_freegame_alreadypost" not in data:
                data["steam_freegame_alreadypost"] = []
            data["steam_freegame_alreadypost"].append(game_id)

    def get_game_id(self, url):
        match = re.search(r"https://store.steampowered.com/app/(\d+)/", url)
        if match:
            game_id = match.group(1)
            return game_id
        else:
            return ""

    @main.before_loop
    async def event_before_loop(self):
        await self.bot.wait_until_ready()

async def setup(client:commands.Bot):
    await client.add_cog(SteamFreeGameCrawler(client))