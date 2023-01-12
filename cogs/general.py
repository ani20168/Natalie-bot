import discord
from discord import app_commands,Embed
from discord.ext import commands
from . import common
from datetime import datetime, timezone, timedelta



class General(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.bot = client


    @app_commands.command(name = "info", description = "關於Natalie...")
    async def info(self,interaction):
        description = """
        你好!我是Natalie!
        以下是我擁有的指令:
        無
        """
        await interaction.response.send_message(embed=Embed(title="我是Natalie!",description=description,color=common.bot_color))

    @commands.Cog.listener()
    async def on_voice_state_update(self,member, before, after):
    #進入語音頻道
        if after.channel and not before.channel:
            embed = Embed(title="", description=f"{member.display_name} 進入了 {after.channel.name} 語音頻道", color=common.bot_color)
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.avatar)
            embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
            await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

        #離開語音頻道
        if before.channel and not after.channel:
            embed = Embed(title="", description=f"{member.display_name} 離開了 {before.channel.name} 語音頻道", color=common.bot_color)
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.avatar)
            embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
            await self.bot.get_channel(common.mod_log_channel).send(embed=embed)

        #切換語音頻道
        if before.channel != after.channel:
            if before.channel and after.channel:
                embed = Embed(title="", description=f"{member.display_name} 從 {before.channel.name} 移動到 {after.channel.name} 頻道", color=common.bot_color)
                embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=member.avatar)
                embed.timestamp = datetime.now(timezone(timedelta(hours=8)))
                await self.bot.get_channel(common.mod_log_channel).send(embed=embed)



async def setup(client:commands.Bot):
    await client.add_cog(General(client))