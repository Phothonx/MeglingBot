"""MeglingBot entry point: logging, bot construction, global error handling."""

import logging
from os import getenv

import discord
from discord import ApplicationContext
from discord.ext import commands
from dotenv import load_dotenv

from megling.extloader import load_extensions
from megling.logsetup import setup_logging

setup_logging()
logger = logging.getLogger("megling.main")

bot = discord.Bot(intents=discord.Intents.all())


@bot.event
async def on_ready():
    infos = await bot.application_info()
    logger.info(
        "App: %s (id %s) | owner: %s | %d guild(s)",
        infos.name,
        infos.id,
        infos.owner.name if infos.owner else "?",
        len(bot.guilds),
    )
    logger.info("Logged in as %s — ready", bot.user)


@bot.event
async def on_application_command_error(ctx: ApplicationContext, error: Exception):
    """Last-resort handler: answer the user and log anything unexpected."""
    # Failed permission/owner checks are expected; refuse quietly.
    if isinstance(error, commands.CheckFailure | discord.CheckFailure):
        if not ctx.interaction.response.is_done():
            await ctx.respond(
                ":interrobang:  **You are not allowed to use this command**", ephemeral=True
            )
        return

    command = ctx.command.qualified_name if ctx.command else "?"
    logger.error("Unhandled error in /%s", command, exc_info=error)
    if not ctx.interaction.response.is_done():
        await ctx.respond(":interrobang:  **Unexpected error!**", ephemeral=True)


BANNER = r"""

 __  __            _ _             ____        _
|  \/  | ___  __ _| (_)_ __   __ _| __ )  ___ | |_
| |\/| |/ _ \/ _` | | | '_ \ / _` |  _ \ / _ \| __|
| |  | |  __| (_| | | | | | | (_| | |_) | (_) | |_
|_|  |_|\___|\__, |_|_|_| |_|\__, |____/ \___/ \__|
             |___/           |___/
             By Algabo & Phothonx.

----------------------------------------------------
Launching MeglingBot...
"""

if __name__ == "__main__":
    logger.info(BANNER)
    load_dotenv()
    token = getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("Missing DISCORD_TOKEN in .env file.")
    # Slash commands are synced automatically on connect (auto_sync_commands=True).
    load_extensions(bot)
    bot.run(token)
