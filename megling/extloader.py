from discord.ext.commands import Bot

extensions = [ "vc", "admin" ]

def loadOne(bot:Bot, extension:str):
  try:
    if extension not in extensions:
      print(f"[?!] Unknown extension: {extension}")
    else:
      extension = f"megling.cogs.{extension}"
      if extension in bot.extensions:
        bot.reload_extension(extension)
      else:
        bot.load_extension(extension)
  except Exception as e:
    print(f"[?!] Failed to load {extension}: {e}")


def loadExtension(bot, extension=None):
  print("(Re)Loading extension(s)...")
  if extension:
    loadOne(bot, extension)
  else:
    for ext in extensions:
      loadOne(bot, ext)
