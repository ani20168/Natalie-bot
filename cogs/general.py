import discord
from discord import app_commands
from discord.ext import commands

class BotSystem(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client


    @app_commands.command(name = "info", description = "關於Natalie...")
    async def info(self,interaction):
        await interaction.response.send_message("我還沒想好這裡要寫什麼......")


async def setup(client:commands.Bot):
    await client.add_cog(BotSystem(client))