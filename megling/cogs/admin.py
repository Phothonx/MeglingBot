from discord.ext import commands
from discord import ApplicationContext, SlashCommandGroup, Bot


class admin(commands.Cog):
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
  print("[~~]Loading admin...")
  bot.add_cog(admin(bot))
  print("[OK] admin loaded")
