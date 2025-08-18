from typing import Literal
from datetime import datetime

from megling.cogs.raidDBManager import RaidDB
from megling.logsetup import setupLogger

from discord import ApplicationContext, SlashCommandGroup, Bot, ui, Embed, Colour, Permissions, SelectOption, Interaction, ButtonStyle
from discord.ext import commands, tasks
from discord.ext.commands import CheckFailure

logger = setupLogger(__name__)
db = RaidDB()

class RaidEmbed(Embed):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple, signups:tuple):
    self.bot = bot
    self.raid = raid
    self.template = template
    self.roles = roles
    self.signups = signups

    raid_id, leader_id, template_name, title, raid_time, message_id, channel_id = self.raid
    template_name, url, description, image, thumbnail, owner_id = self.template

    super().__init__(
      colour=Colour.blue(),
      url=url,
      description=description,
      title=title,
      timestamp=datetime.now()
    )

    self.set_footer(text=template_name)
    if image:
      self.set_image(url=image)
    if thumbnail:
      self.set_thumbnail(url=thumbnail)

  @classmethod
  async def create(cls, bot, raid_id: int):
    raid = await db.get_raid(raid_id)
    raid_id, leader_id, template_name, title, raid_time, message_id, channel_id = raid
    template = await db.get_template(template_name)
    roles = await db.get_template_roles(template_name)
    signups = await db.get_signups(raid_id)

    embed = cls(bot, raid, template, roles, signups)

    await embed.set_embed_author()
    await embed.set_fields()
    return embed

  async def set_embed_author(self):
    raid_id, leader_id, template_name, title, raid_time, message_id, channel_id = self.raid
    user = await self.bot.fetch_user(leader_id)
    user_name = user.name if user else f"<@{leader_id}>"
    self.set_author(name=user_name)


  async def set_fields(self):
    raid_id, leader_id, template_name, title, raid_timer, message_id, channel_id = self.raid
    template_name, url, description, image, thumbnail, owner_id = self.template
    self.add_field(name=f"<t:{int(raid_timer.timestamp())}:R>", value="")

    total_signed = 0
    max_raid_slots = 0

    for role in self.roles:
      role_name, role_icon, max_slots = role
      role_signups = []

      for signup in self.signups:
        user_id, signup_role_name, signup_time, signup_rank = signup
        if signup_role_name == role_name:
          user = await self.bot.fetch_user(user_id)
          user_name = user.name if user else f"<@{user_id}>"
          role_signups.append(f"**{signup_rank}** {user_name}")

      total_signed += len(role_signups)
      max_raid_slots += max_slots
      role_signups.sort()
      value = "\n".join(role_signups) or "—"
      self.add_field(name=f":{role_icon}: {role_name} {len(role_signups)}/{max_slots}", value=value)

    self.insert_field_at(index=1, name=f"{total_signed}/{max_raid_slots}", value="")
    self.insert_field_at(index=1, name="", value="")


# maybe add caching to get templates and roles to avoid useless requests, later

class RoleSelector(ui.Select):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple):
    self.bot = bot
    self.raid = raid
    self.template = template
    self.roles = roles
    options = [
      SelectOption(label=role_name, value=role_name) # emoji=role_icon, 
      for role_name, role_icon, max_slots in self.roles
    ]
    super().__init__(
      placeholder="Chose a role to signup",
      min_values=1,
      max_values=1,
      options=options
    )

  async def callback(self, interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    raid_id, leader_id, template_name, title, raid_time_str, message_id, channel_id = self.raid
    role_name = self.values[0]
    await db.signup_user(user_id=user_id, raid_id=raid_id, role_name=role_name)

    embed = await RaidEmbed.create(self.bot, raid_id)
    view = await RaidView.create(self.bot, raid_id)

    channel = await self.bot.fetch_channel(channel_id)
    message = await channel.fetch_message(message_id)
    await message.edit(embed=embed, view=view)
    await interaction.response.send_message("✅ Signed up!", ephemeral=True)



class AbsenceButton(ui.Button):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple):
    self.bot = bot
    self.raid = raid
    self.template = template
    self.roles = roles
    super().__init__(
      label="Absent",
      style=ButtonStyle.red
    )

  async def callback(self, interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    raid_id, leader_id, template_name, title, raid_time_str, message_id, channel_id = self.raid
    await db.signup_user(user_id=user_id, raid_id=raid_id, role_name="absent")

    embed = await RaidEmbed.create(self.bot, raid_id)
    view = await RaidView.create(self.bot, raid_id)

    channel = await self.bot.fetch_channel(channel_id)
    message = await channel.fetch_message(message_id)
    await message.edit(embed=embed, view=view)
    await interaction.response.send_message("✅ Signed up!", ephemeral=True)



class RaidView(ui.View):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple) -> None:
    super().__init__(timeout=None)
    self.add_item(RoleSelector(bot, raid, template, roles))
    self.add_item(AbsenceButton(bot, raid, template, roles))


  @classmethod
  async def create(cls, bot, raid_id: int):
    raid = await db.get_raid(raid_id)
    raid_id, leader_id, template_name, title, raid_time, message_id, channel_id = raid
    template = await db.get_template(template_name)
    roles = await db.get_template_roles(template_name)

    view = cls(bot, raid, template, roles)
    return view



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


  template = SlashCommandGroup("template", description="Create and edit raid templates")


  @template.command(name="create", default_member_permissions=Permissions(administrator=True))
  async def create(self, ctx: ApplicationContext, template_name:str, url:str, description:str, image:str, thumbnail:str):
    user_id = ctx.user.id
    await db.create_template(template_name=template_name, url=url, description=description, image=image, thumbnail=thumbnail, owner_id=user_id)
    await ctx.respond(f"✅ Template `{template_name}` created.", ephemeral=True)


  @template.command(name="role", default_member_permissions=Permissions(administrator=True))
  async def role(self, ctx: ApplicationContext, template_name:str, role_name:str, role_icon:str, max_slots:int):
    # verify user is owner of the template
    await db.add_template_role(template_name=template_name, role_name=role_name, role_icon=role_icon, max_slots=max_slots)
    await ctx.respond(f"✅ Template role `{role_name}` created for {template_name}.", ephemeral=True)



  raid = SlashCommandGroup("raid", description="Manage and start raids")


  @raid.command(name="start", default_member_permissions=Permissions(administrator=True))
  async def start(self, ctx: ApplicationContext, template_name:str, title:str, user_raid_time:str):
    await ctx.defer()
    user_id = ctx.user.id
    raid_time = datetime.strptime(user_raid_time, "%Y-%m-%d %H:%M")
    msg = await ctx.channel.send("*making raid...*")
    raid_id = await db.add_raid(leader_id=user_id, template_name=template_name, title=title, raid_time=raid_time, message_id=msg.id, channel_id=msg.channel.id)
    embed = await RaidEmbed.create(bot=self.bot, raid_id=raid_id)
    view = await RaidView.create(bot=self.bot, raid_id=raid_id)
    await msg.edit(content="", embed=embed, view=view)
    await ctx.respond("raid created")


def setup(bot: Bot):
  logger.info("[~~] Loading Raid...")
  bot.add_cog(Raid(bot))
  logger.info("[OK] Raid loaded")
