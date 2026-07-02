"""Loads and reloads the bot's feature extensions (cogs)."""

import logging

from discord import Bot

logger = logging.getLogger(__name__)

extensions = ["voice", "admin", "views", "raid"]


def _load_one(bot: Bot, name: str) -> None:
    if name not in extensions:
        logger.warning("Unknown extension: %s", name)
        return

    module = f"megling.cogs.{name}"
    try:
        if module in bot.extensions:
            bot.reload_extension(module)
            logger.info("Reloaded extension: %s", name)
        else:
            bot.load_extension(module)
            logger.info("Loaded extension: %s", name)
    except Exception:
        logger.exception("Failed to load extension: %s", name)


def load_extensions(bot: Bot, name: str | None = None) -> None:
    """(Re)load one extension by name, or every known extension if none is given."""
    if name:
        _load_one(bot, name)
    else:
        for ext in extensions:
            _load_one(bot, ext)
