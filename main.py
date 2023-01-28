import megling
from megling import getconfig

import discord
from discord.ext import commands

import os
from dotenv import load_dotenv

# START
print("""

 __  __            _ _             ____        _
|  \/  | ___  __ _| (_)_ __   __ _| __ )  ___ | |_
| |\/| |/ _ \/ _` | | | '_ \ / _` |  _ \ / _ \| __|
| |  | |  __| (_| | | | | | | (_| | |_) | (_) | |_
|_|  |_|\___|\__, |_|_|_| |_|\__, |____/ \___/ \__|
             |___/           |___/
             By YagooSRV & Phothonx.


Launching MeglingBot...
----------------------------------------------------""")

# INTENTS & COMMAND PREFIX
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=megling.getconfig.getPrefix(), intents=intents, help_command=None)


# ON READY & COGS
@bot.event
async def on_ready():
    print("----------------------------------------------------\nMeglingBot successfully connected !\n")
    
    print("Loading extentions...")
    path = os.getcwd()
    loadNb = 0
    for files in os.listdir(f"{path}\\megling\\cogs"):
        if files.endswith(".py"):   
            try:
               await bot.load_extension(f"megling.cogs.{files[:-3]}")
               loadNb += 1
            except:
                print(f"Failed to load {files[:-3]} !")
    print(f"Loaded {loadNb} extentions !\n")

    await bot.change_presence(status=discord.Status.online, activity=discord.Game(name="/megling"))

    print("Syncing Slash commands...")
    synced = await bot.tree.sync()
    print(f"Synced {str(len(synced))} commands !\n")


# COGS RELOADERS (TESTS)
@bot.command()
async def load(ctx, extension):
    try:
        await bot.load_extension(f'megling.cogs.{extension}')
        await ctx.send(f"**:white_check_mark:  Cog {extension} loaded.**")
    except:
        await ctx.send(f"**:interrobang:  Failed to load Cog {extension}.**")

@bot.command()
async def unload(ctx, extension):
    try:
        await bot.unload_extension(f'megling.cogs.{extension}')
        await ctx.send(f"**:x:  Cog {extension} unloaded.**")
    except:
        await ctx.send(f"**:interrobang:  Failed to unload Cog {extension}.**")

@bot.command()
async def reload(ctx, extension):
    try:
        await bot.unload_extension(f'megling.cogs.{extension}')
        await bot.load_extension(f'megling.cogs.{extension}')
        await ctx.send(f"**:arrows_clockwise:  Cog {extension} reloaded.**")
    except:
        await ctx.send(f"**:interrobang:  Failed to reload Cog {extension}.**")

@bot.tree.command(
    name="ping",
    descriptin="Renvoie le ping du bot"
)
async def ping(Interaction : discord.Interaction):
    await Interaction.response.send_message(f"**:inbox_tray:  Pong avec {round(bot.latency * 1000)} ms.**")


# RUN
try :
    bot.run(megling.getconfig.getToken())
except :
    print("MeglingBot failed to connect !")