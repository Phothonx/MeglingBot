import discord
from discord.ext import commands


class errorHandle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    #   await ctx.send("**:interrobang:  YY**")
        
    @commands.Cog.listener()
    async def on_app_command_error(self, ctx : commands.Context, error):
        if isinstance(error, commands.BadArgument):
            pass
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.CheckFailure):
            pass
        elif isinstance(error, commands.DisabledCommand):
            pass
        elif isinstance(error, commands.CommandOnCooldown):
            pass
        elif isinstance(error, commands.MaxConcurrencyReached):
            pass
        else:
            await ctx.send("**:interrobang:  An unknown error has occurred.**")


    

async def setup(bot):
    await bot.add_cog(errorHandle(bot))


