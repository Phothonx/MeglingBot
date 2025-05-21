import discord
from discord.ext import commands


class admin(commands.Cog):
  def __init__(self, bot):
      self.bot = bot


  @commands.hybrid_command()
  @commands.is_owner()
  async def prune(self, ctx, number=5):
    await ctx.channel.purge(limit=int(number))


async def setup(bot):
  print("Loading admin...")
  await bot.add_cog(admin(bot))
  print("[OK] admin loaded")
