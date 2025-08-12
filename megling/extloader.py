from discord.ext.commands import Bot
from megling.logsetup import setupLogger

logger = setupLogger(__name__)

extensions = [ "vc", "admin", "views" ]

def loadOne(bot:Bot, extension:str):
  try:
    if extension not in extensions:
      logger.info(f"[?!] Unknown extension: {extension}")
    else:
      extension = f"megling.cogs.{extension}"
      if extension in bot.extensions:
        bot.reload_extension(extension)
      else:
        bot.load_extension(extension)
  except Exception as e:
    logger.error(f"[?!] Failed to load {extension}: {e}")


def loadExtension(bot, extension=None):
  logger.info("(Re)Loading extension(s)...")
  if extension:
    loadOne(bot, extension)
  else:
    for ext in extensions:
      loadOne(bot, ext)
