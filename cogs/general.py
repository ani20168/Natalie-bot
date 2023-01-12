import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common



class BotSystem(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client


    @app_commands.command(name = "info", description = "關於Natalie...")
    async def info(self,interaction):
        await interaction.response.send_message("我還沒想好這裡要寫什麼......")

    @app_commands.command(name="shutdown", description = "關閉機器人" )
    async def shutdown(self,interaction):
        if interaction.user.id == common.bot_owner_id:
            await interaction.response.send_message(embed=Embed(title="系統操作",description="我要睡著了...",color=common.bot_color))
            await self.bot.close()
        else: 
            await interaction.response.send_message(embed=Embed(title="系統操作",description="權限不足。",color=common.bot_color))


async def setup(client:commands.Bot):
    await client.add_cog(BotSystem(client))