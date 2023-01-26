import discord
from discord.ext import commands


class example(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    async def test(self, ctx):
        await ctx.send("**:ok_hand:  This test is successfull**")

    @commands.Cog.listener()
    async def on_ready(self):
        print("Cog example loaded !")


async def setup(bot):
    await bot.add_cog(example(bot))