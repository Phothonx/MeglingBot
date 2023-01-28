import megling
from megling import getconfig

import colorama
from colorama import Fore

import os
import discord
from discord.ext import commands

# colorama
colorama.init(autoreset=True)

# START
print(f"""{Fore.BLUE}{colorama.Style.BRIGHT}

 __  __            _ _             ____        _
|  \/  | ___  __ _| (_)_ __   __ _| __ )  ___ | |_
| |\/| |/ _ \/ _` | | | '_ \ / _` |  _ \ / _ \| __|
| |  | |  __| (_| | | | | | | (_| | |_) | (_) | |_
|_|  |_|\___|\__, |_|_|_| |_|\__, |____/ \___/ \__|
             |___/           |___/
             By Algabo & Phothonx.


{Fore.CYAN}Launching MeglingBot...
----------------------------------------------------""")

# INTENTS & COMMAND PREFIX
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=megling.getconfig.getPrefix(), intents=intents, help_command=None)


# ON READY
@bot.event
async def on_ready():
    print(f"{Fore.CYAN}----------------------------------------------------\n{Fore.GREEN}MeglingBot successfully connected !\n")

# LOADING COGS  
    print(f"{Fore.CYAN}Loading extentions...")
    loadNb = 0
    for files in os.listdir(f"{megling.getconfig.getPath()}\\megling\\cogs"):
        if files.endswith(".py"):
            try:
               await bot.load_extension(f"megling.cogs.{files[:-3]}")
               loadNb += 1
            except:
                print(f"{Fore.RED}Failed to load {files[:-3]} !")
    print(f"{Fore.GREEN}Loaded {loadNb} extentions !\n")

    await bot.change_presence(status=discord.Status.online, activity=discord.Game(name="/megling"))

    print(f"{Fore.CYAN}Syncing Slash commands...")
    synced = await bot.tree.sync()
    print(f"{Fore.GREEN}Synced {str(len(synced))} commands !\n")


# PING /COMMAND
@bot.tree.command(
    name="ping",
    description="Return Megling's ping"
)
async def ping(Interaction : discord.Interaction):
    await Interaction.response.send_message(f"**:inbox_tray:  Pong with {round(bot.latency * 1000)} ms.**")


# RUN
try :
    bot.run(megling.getconfig.getToken())
except :
    print(f"{Fore.RED}MeglingBot failed to connect !")