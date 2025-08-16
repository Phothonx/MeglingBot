from re import template
from shlex import join
from typing import Literal
import aiosqlite
import disco
from datetime import datetime
from megling.cogs.raidDBManager import RaidDB

from megling.logsetup import setupLogger

from discord.ext.commands import CheckFailure
from discord import ApplicationContext, SlashCommandGroup, Bot, ui, Embed, EmbedAuthor, EmbedMedia, EmbedFooter, Colour, get_user
from discord.ext import commands

logger = setupLogger(__name__)

db = RaidDB()

class RaidEmbed(Embed):
  def __init__(self, raidID):
    raid = db.get_raid(raidID)
    self.raidID = raidID
    self.template = db.get_template(raid[2])
    super().__init__(
      colour=Colour.blue,
      url=self.template[1] if self.template[1] else None,
      description=self.template[2] if self.template[2] else None,
      title=raid[3],
      timestamp=datetime.now()
    )
    self.set_footer(text=self.template[0])
    self.set_author(name=raid[1])
    if self.template[3]:
      self.set_image(url=self.template[3])
    if self.template[4]:
      self.set_thumbnail(url=self.template[4])

  async def update(self):
    raid = db.get_raid(self.raidID)
    roles = db.get_template_roles(raid[2])
    signups = db.get_signups(self.raidID)

    self.clear_fields()

    self.add_field(name=f"<t:{str(raid[4])}:R>", value="")

    max = 0
    for role in roles:
      role_signups = []
      max+= role[3]
      for signup in signups:
        if signup[3] = role[1]
          userName = await get_user(signup[1]).name
          role_signups.append(f"{signup[6]} {userName}")
      role_signups.sort() # will sort according to signup rank (will be issues >10 idc)
      self.add_field(name=f":{role[2]}: {role[1]}", value="\n".join(role_signups)+"\n")

    self.insert_field_at(index=1, name=f"{raid[5]}/{max} raiders", value="")


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
    db.checkup()


  template = SlashCommandGroup("temlpate", description="Create and edit raid temlpates")


  template.command(name="crate")
  async def create(self, ctx: ApplicationContext, templateName:str, url:str|None, description:str|None, image:str|None, thumbnail:str|None):
    userID = ctx.user.id
    db.create_template(templateName=templateName, url=url, description=description, image=image, thumbnail=thumbnail, ownerID=userID):


  raid = SlashCommandGroup("raid", description="Manage and start raids")


  @raid.command(name="start")
  async def start(self, ctx: ApplicationContext, templateName:str, title:str, raidTime:str):
    userID = ctx.user.id
    raidTime = datetime.now() # change later
    db.add_raid(leaderId=userID, templateName=templateName, title=title, raidTime=raidTime)
    embed = RaidEmbed()
    ctx.channel.send(embed=RaidEmbed)
    embed.update()


def setup(bot: Bot):
  logger.info("[~~] Loading Raid...")
  bot.add_cog(Raid(bot))
  logger.info("[OK] Raid loaded")
