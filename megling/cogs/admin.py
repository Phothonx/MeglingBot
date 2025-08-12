from discord.ext import commands
from discord import ApplicationContext, SlashCommandGroup, Bot
from megling.logsetup import setupLogger

logger = setupLogger(__name__)

class Admin(commands.Cog):
  def __init__(self, bot:Bot):
      self.bot = bot

  admin = SlashCommandGroup("admin", description="Admin commands")

  @admin.command()
  @commands.is_owner()
  async def prune(self, ctx:ApplicationContext, number:int=5):
    await ctx.defer(ephemeral=True)
    await ctx.channel.purge(limit=int(number))
    await ctx.followup.send(":white_check_mark:  **Done**", ephemeral=True)


def setup(bot:Bot):
  logger.info("[~~]Loading Admin...")
  bot.add_cog(Admin(bot))
  logger.info("[OK] Admin loaded")
