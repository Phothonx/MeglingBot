import discord
from discord.ext import commands

class example(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    


    @commands.Cog.listener()
    async def on_ready(self):
        print("Cog example loaded !")



async def setup(bot):
    await bot.add_cog(example(bot))