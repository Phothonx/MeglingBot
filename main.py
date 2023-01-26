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

# INTENTS
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=megling.getconfig.getPrefix(), intents=intents, help_command=None)

# STATUS


# ON READY & COGS
@bot.event
async def on_ready():
    print("----------------------------------------------------\nMeglingBot successfully connected !\nLoading cogs...")
    path = os.getcwd()
    for files in os.listdir(f"{path}\\megling\\cogs"):
        if files.endswith(".py"):   
            try:
               await bot.load_extension(f"megling.cogs.{files[:-3]}")
            except:
                print(f"Failed to load {files[:-3]} !")
    print("All cogs loadded !")

# RUN
try :
    bot.run(megling.getconfig.getToken())
except :
    print("MeglingBot failed to connect !")