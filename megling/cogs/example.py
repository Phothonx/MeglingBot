import discord
from discord.ext import commands


class example(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(
        name="test",
        description="Fait un test"
    )
    async def test(self, ctx):
        await ctx.send("**:ok_hand:  This test is successfull**")

async def setup(bot):
    await bot.add_cog(example(bot))