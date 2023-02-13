import discord
from discord.ext import commands


class settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    commands.tree.command(
        name="setRole",
        description="Edit Megling's Settings"
    )
    async def setRole(Interaction : discord.Interaction(),perm : str, role : discord.Role):
        if lower(role) == Admin:
            pass
        elif lower(role) == Manager:
            pass

async def setings(bot):
    await bot.admin(admin(bot))