from typing import Literal
from datetime import datetime

from megling.cogs.raidDBManager import RaidDB
from megling.logsetup import setupLogger

from discord import ApplicationContext, SlashCommandGroup, Bot, ui, Embed, Colour
from discord.ext import commands, tasks
from discord.ext.commands import CheckFailure

logger = setupLogger(__name__)

db = RaidDB()

class RaidEmbed(Embed):
  def __init__(self, bot, raid, template):
    self.bot = bot
    super().__init__(
      colour=Colour.blue(),
      url=template[1] if template[1] else None,
      description=template[2] if template[2] else None,
      title=raid[3],
      timestamp=datetime.now()
    )
    self.raidID = raid[0]
    self.template = template

    self.set_footer(text=template[0])
    self.set_author(name=str(raid[1]))  # leader id, ideally fetch name
    if template[3]:
      self.set_image(url=template[3])
    if template[4]:
      self.set_thumbnail(url=template[4])

  @classmethod
  async def create(cls, bot, raid_id: int):
    raid = await db.get_raid(raid_id)
    template = await db.get_template(raid[2])
    print(raid)
    print(template)
    return cls(bot, raid, template)

  async def update_embed(self):
    print("updating")
    raid = await db.get_raid(self.raidID)
    roles = await db.get_template_roles(raid[2])
    signups = await db.get_signups(self.raidID)
    print(roles)
    print(signups)
    print(raid)

    self.clear_fields()
    self.add_field(name=f"<t:{int(raid[4].timestamp())}:R>", value="")
    print("added fields")

    total_signed = 0
    max_slots = 0

    for role in roles:
      rolename, roleicon, maxslots = role
      role_signups = []

      for signup in signups:
        if signup[1] == rolename:
          user = await bot.get_user(signup[0])
          username = user.name if user else f"<@{signup[0]}>"
          role_signups.append(f"{signup[4]} {username}")

      total_signed += len(role_signups)
      max_slots += maxslots
      role_signups.sort()
      value = "\n".join(role_signups) or "—"
      self.add_field(name=f":{roleicon}: {rolename}", value=value)

    print("insert member count")
    self.insert_field_at(index=1, name=f"{total_signed}/{max_slots} raiders", value="")

class RaidView(ui.View):
  def __init__(self):
    super().__init__(timeout=None)


class Raid(commands.Cog):
  def __init__(self, bot: Bot):
    self.bot = bot
    self.checkuploop.start()

  def cog_unload(self):
    self.checkuploop.cancel()

  @tasks.loop(hours=24)
  async def checkuploop(self):
    await db.checkup()

  @checkuploop.before_loop
  async def before_checkup(self):
    await self.bot.wait_until_ready()


  template = SlashCommandGroup("template", description="Create and edit raid temlpates")


  @template.command(name="create")
  async def create(self, ctx: ApplicationContext, templatename:str, url:str, description:str, image:str, thumbnail:str):
    userID = ctx.user.id
    await db.create_template(templateName=templatename, url=url, description=description, image=image, thumbnail=thumbnail, ownerID=userID)
    await ctx.respond(f"✅ Template `{templatename}` created.", ephemeral=True)


  raid = SlashCommandGroup("raid", description="Manage and start raids")


  @raid.command(name="start")
  async def start(self, ctx: ApplicationContext, templatename:str, title:str, raidtime:str):
    userID = ctx.user.id
    raid_time = datetime.strptime(raidtime, "%Y-%m-%d %H:%M")
    raid_id = await db.add_raid(leaderId=userID, templateName=templatename, title=title, raidTime=raid_time)
    embed = await RaidEmbed.create(bot=self.bot, raid_id=raid_id)
    await ctx.defer()
    msg = await ctx.channel.send(embed=embed)
    await embed.update_embed()
    await msg.edit(embed=embed) # maybe put this in the RaidEmbed class to auto edit itself
    await ctx.respond("done")


def setup(bot: Bot):
  logger.info("[~~] Loading Raid...")
  bot.add_cog(Raid(bot))
  logger.info("[OK] Raid loaded")
