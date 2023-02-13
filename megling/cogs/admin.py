import discord
from discord.ext import commands


class admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.tree.command(
        name="kick",
        description="Kick someone from the server"
    )
    async def kick(Interaction : discord.Interaction, user : discord.User, reason : str):
        await Interaction.Guild.kick(user=user, reason=reason )



    

async def setup(bot):
    await bot.admin(admin(bot))