import discord

from discord.ext import commands
from os import getenv
from dotenv import load_dotenv
from megling.extloader import loadExtension

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.hybrid_command()
@commands.is_owner()
async def reload(ctx, extension=None):
  await loadExtension(bot, extension)


@bot.hybrid_command()
async def ping(ctx):
    await ctx.send(f"**:inbox_tray:  Pong with {round(bot.latency * 1000)} ms.**")


@bot.event
async def on_ready():
  infos = await bot.application_info()
  print(f"""
------------------- APP INFO -----------------------
APP NAME : {infos.name}
APP ID : {infos.id}
OWNER ID : {infos.owner.name}
APP TEAM : {infos.name}
GUILDS :
----------------------------------------------------\n""")
  await loadExtension(bot)
  print(f'[OK] Logged in as {bot.user}\n')


if __name__ == "__main__":
  print(r"""

 __  __            _ _             ____        _
|  \/  | ___  __ _| (_)_ __   __ _| __ )  ___ | |_
| |\/| |/ _ \/ _` | | | '_ \ / _` |  _ \ / _ \| __|
| |  | |  __| (_| | | | | | | (_| | |_) | (_) | |_
|_|  |_|\___|\__, |_|_|_| |_|\__, |____/ \___/ \__|
             |___/           |___/
             By Algabo & Phothonx.

----------------------------------------------------
Launching MeglingBot...
""")
  load_dotenv()
  TOKEN = getenv("DISCORD_TOKEN")
  bot.run(TOKEN)
