extensions = [ "vc", "admin" ]

async def loadOne(bot, extension=None):
  try:
    extension = f"megling.cogs.{extension}"
    if extension in bot.extensions:
      await bot.reload_extension(extension)
    else:
      await bot.load_extension(extension)
  except:
    print(f"[?!] Failed to load {extension}!")

async def loadExtension(bot, extension=None):
  print("(Re)Loading extension(s)...")
  if extension:
    await loadOne(bot, extension)
  else:
    for extension in extensions:
      await loadOne(bot, extension)
  print("[OK] Extension(s) (Re)loaded")
  print("Syncing Slash commands...")
  await bot.tree.sync()
  print("[OK] Synced commands\n")
