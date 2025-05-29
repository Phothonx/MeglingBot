from discord import Intents, ApplicationContext
from discord.ext.commands import CommandError

from discord.ext import commands
from os import getenv
from dotenv import load_dotenv
from megling.extloader import loadExtension
from megling.logsetup import setupLogger

logger = setupLogger(__name__)

intents = Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

async def syncCommands():
  logger.info("[~~] Syncing Slash commands...")
  await bot.sync_commands()
  logger.info("[OK] Synced commands\n")

@bot.slash_command(name="reload", description="Reload the bot")
@commands.is_owner()
async def reload( ctx: ApplicationContext, extension:str|None=None ):
  await ctx.defer(ephemeral=True)
  loadExtension(bot, extension)
  await syncCommands()
  await ctx.followup.send(f":arrows_clockwise:  **Reloading: {extension}**" if extension else ":arrows_clockwise:  **Reloading all**")


@bot.slash_command(name="ping", description="Ping the bot")
async def ping(ctx:ApplicationContext):
    await ctx.respond(f"**:inbox_tray:  Pong with {round(bot.latency * 1000)} ms.**")


@bot.event
async def on_command_error(ctx: ApplicationContext, error: CommandError):
  await ctx.respond(":interrobang: **Unexpected Error!**", ephemeral=True)
  logger.error(f"[?!] Unhandled command error: {error}")
  # raise error

@bot.event
async def on_ready():
  infos = await bot.application_info()
  logger.info(f"""

------------------- APP INFO -----------------------
APP NAME : {infos.name}
APP ID : {infos.id}
OWNER ID : {infos.owner.name}
GUILDS : {len(bot.guilds)} servers
----------------------------------------------------
""")
  loadExtension(bot)
  await syncCommands()
  logger.info(f"""

[OK] Logged in as {bot.user}
----------------------------------------------------
""")


if __name__ == "__main__":
  logger.info(r"""

 __  __            _ _             ____        _
|  \/  | ___  __ _| (_)_ __   __ _| __ )  ___ | |_
| |\/| |/ _ \/ _` | | | '_ \ / _` |  _ \ / _ \| __|
| |  | |  __| (_| | | | | | | (_| | |_) | (_) | |_
|_|  |_|\___|\__, |_|_|_| |_|\__, |____/ \___/ \__|
             |___/           |___/
             By Algabo & Phothonx.

----------------------------------------------------
[~~] Launching MeglingBot...
""")
  load_dotenv()
  TOKEN = getenv("DISCORD_TOKEN")
  if not TOKEN:
    raise ValueError("Missing DISCORD_TOKEN in .env file.")
  bot.run(TOKEN)
