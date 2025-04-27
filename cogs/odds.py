import discord
from discord import app_commands,Embed
from discord.ext import commands,tasks
from . import common
import os
import time
import asyncio

odds_filelock = asyncio.Lock()

class OddService(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client
        self.save_path = "data/odds.json"



async def setup(client:commands.Bot):
    await client.add_cog(OddService(client))