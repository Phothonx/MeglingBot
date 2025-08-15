from typing import Literal
import aiosqlite
from datetime import datetime
from megling.cogs.raidDBManager import RaidDB

from megling.logsetup import setupLogger

from discord.ext.commands import CheckFailure
from discord import ApplicationContext, SlashCommandGroup, Bot, ui, Embed, EmbedAuthor, EmbedMedia, EmbedFooter, Colour
from discord.ext import commands

logger = setupLogger(__name__)

db = RaidDB()

class RaidEmbed(Embed):
  def __init__(self, raidID):
    raid = db.get_raid(raidID)
    super().__init__(
      colour=Colour.blue,
    )

class RaidView(ui.View):
  def __init__(self):
    super().__init__(timeout=None)


class Raid(commands.Cog):
  def __init__(self, bot: Bot):
    self.bot = bot

  def cog_unload(self):
    self.checkuploop().cancel()

  @tasks.loop(hours=24)
  async def checkuploop(self):
    pass

  @checkuploop.before_loop
  async def first_checkup(self):
    pass


  raid = SlashCommandGroup("raid", description="Manage and start raids")

  @raid.command(name="start")
    async def start(self, ctx: ApplicationContext)


def setup(bot: Bot):
  logger.info("[~~] Loading Raid...")
  bot.add_cog(Raid(bot))
  logger.info("[OK] Raid loaded")
