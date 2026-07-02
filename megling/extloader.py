"""Loads and reloads the bot's feature extensions (cogs)."""

import importlib
import logging
import sys

from discord import Bot

logger = logging.getLogger(__name__)

extensions = ["voice", "admin", "owner", "embed", "rolemenu", "raid"]


def _reload_shared_modules() -> None:
    """Re-import the non-cog megling modules (db managers, utils).

    reload_extension only re-imports the cog module itself; without this, a
    hot-reloaded cog keeps using the stale classes cached in sys.modules.
    Parents sort before children, so packages reload before their contents.
    """
    for module_name in sorted(sys.modules):
        if (
            module_name.startswith("megling.")
            and ".cogs" not in module_name
            and module_name != __name__
        ):
            importlib.reload(sys.modules[module_name])
    logger.info("Reloaded shared modules")


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
    if bot.extensions:  # this is a hot reload: refresh support modules first
        _reload_shared_modules()
    if name:
        _load_one(bot, name)
    else:
        for ext in extensions:
            _load_one(bot, ext)
