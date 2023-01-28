import megling
from megling import getconfig

import os
import discord
from discord.ext import commands


class reloader(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def allCogs(self, loadtype):
        loadNb = 0
        loadfails = []
        for files in os.listdir(f"{megling.getconfig.getPath()}\\megling\\cogs"):
            if files.endswith(".py") and files != "reloader.py":
                try:
                    await loadtype(f"megling.cogs.{files[:-3]}")
                    loadNb += 1
                except:
                    loadfails.append(files)    
        return loadNb, loadfails

    @commands.command(
        name="load",
        aliases=["ld"],
        description="Load one/all extension/s"
    )
    async def load(self, ctx, extension = None):
        if extension:
            try:
                await self.bot.load_extension(f'megling.cogs.{extension}')
                await ctx.send(f"**:white_check_mark:  Extension {extension} loaded.**")
            except:
                await ctx.send(f"**:interrobang:  Failed to load extension {extension}.**")
        else:
            loadNb, loadfails = await self.allCogs(self.bot.load_extension)
            await ctx.send(f"**:white_check_mark:  {loadNb} extensions loaded.**")
            if loadfails:
                await ctx.send(f"**:interrobang:  Failed to load {str(len(loadfails))} extensions.**")
            

    @commands.command(
        name="unload",
        aliases=["ul"],
        descriptin="Unload one/all extension/s"
    )
    async def unload(self, ctx, extension = None):
        if extension:
            try:
                await self.bot.unload_extension(f'megling.cogs.{extension}')
                await ctx.send(f"**:x:  Extension {extension} unloaded.**")
            except:
                await ctx.send(f"**:interrobang:  Failed to unload extension {extension}.**")
        else:
            loadNb, loadfails = await self.allCogs(self.bot.unload_extension)
            await ctx.send(f"**:x:  {loadNb} extensions unloaded.**")
            if loadfails:
                await ctx.send(f"**:interrobang:  Failed to unload {str(len(loadfails))} extensions.**")


    @commands.command(
        name="reload",
        aliases=["rl"],
        descriptin="Reload one/all extension/s"
    )
    async def reload(self, ctx, extension = None):
        if extension:
            try:
                await self.bot.reload_extension(f'megling.cogs.{extension}')
                await ctx.send(f"**:arrows_clockwise:  Extension {extension} reloaded.**")
            except:
                await ctx.send(f"**:interrobang:  Failed to reload extension {extension}.**")
        else:
            loadNb, loadfails = await self.allCogs(self.bot.reload_extension)
            await ctx.send(f"**:arrows_clockwise:  {loadNb} extensions reloaded.**")
            if loadfails:
                await ctx.send(f"**:interrobang:  Failed to reload {str(len(loadfails))} extensions.**")

async def setup(bot):
    await bot.add_cog(reloader(bot))