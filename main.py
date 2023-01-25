import megling
from megling import getconfig

import discord
from discord.ext import commands

import os
from dotenv import load_dotenv


print("""
----------------------------------------------------
 __  __            _ _             ____        _
|  \/  | ___  __ _| (_)_ __   __ _| __ )  ___ | |_
| |\/| |/ _ \/ _` | | | '_ \ / _` |  _ \ / _ \| __|
| |  | |  __| (_| | | | | | | (_| | |_) | (_) | |_
|_|  |_|\___|\__, |_|_|_| |_|\__, |____/ \___/ \__|
             |___/           |___/
             By YagooSRV & Phothonx.
----------------------------------------------------

Launching MeglingBot...""")



intents = discord.Intents.all()
bot = commands.Bot(command_prefix=megling.getconfig.getPrefix(), intents=intents, help_command=None)

try :
    bot.run(megling.getconfig.getToken())
    print("MeglingBot successfully launched !")
except :
    print("MeglingBot failed to launched !")