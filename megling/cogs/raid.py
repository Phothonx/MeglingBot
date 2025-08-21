from typing import Literal
import re
import unicodedata
from datetime import datetime

from megling.cogs.raidDBManager import RaidDB
from megling.logsetup import setupLogger

from discord import ApplicationContext, SlashCommandGroup, Bot, ui, Embed, Colour, Permissions, SelectOption, Interaction, ButtonStyle, Option, guild_only, PartialEmoji, InputTextStyle
from discord.ext import commands, tasks
from discord.ext.commands import CheckFailure

logger = setupLogger(__name__)
db = RaidDB()


CUSTOM_EMOJI_PATTERN = re.compile(r"^<a?:\w+:\d+>$")
def is_custom_discord_emoji(s: str) -> bool:
  return bool(CUSTOM_EMOJI_PATTERN.fullmatch(s.strip()))

def is_unicode_emoji(s: str) -> bool:
  if len(s) == 0:
    return False
  # Check if every character has a "So" (Symbol, other) Unicode category
  return all(unicodedata.category(char) in {"So", "Sk"} for char in s)

def parse_emoji(s: str) -> PartialEmoji | None:
  s = s.strip()
  if is_custom_discord_emoji(s):
    try:
      return PartialEmoji.from_str(s)
    except Exception:
      return None
  elif is_unicode_emoji(s):
    return PartialEmoji(name=s)
  return None

class RaidModal(ui.Modal):
  def __init__(self, bot: Bot, user_id: int):
    super().__init__(title="Lancer un Raid")
    self.bot = bot
    self.user_id = user_id

    self.template_name_input = ui.InputText(
      label="Nom du modèle à utiliser",
      placeholder="Ex: mon_template",
      required=True,
      max_length=50
    )

    self.title_input = ui.InputText(
      label="Titre du raid (Capitalisé automatiquement)",
      placeholder="Ex: Dragon Millénaire",
      required=True,
      max_length=100
    )
    self.raid_time_input = ui.InputText(
      label="Date et heure (YYYY-MM-DD HH:MM, format ISO)",
      value=datetime.now().isoformat(),
      required=True,
      max_length=30
    )

    self.add_item(self.template_name_input)
    self.add_item(self.title_input)
    self.add_item(self.raid_time_input)

  async def callback(self, interaction: Interaction):
    template_name = self.template_name_input.value.strip()
    title = self.title_input.value.strip()
    raid_time_str = self.raid_time_input.value.strip()

    try:
      raid_time = datetime.fromisoformat(raid_time_str)
    except ValueError:
      await interaction.response.send_message(f":x: **La date n'est pas au format ISO 8601**", ephemeral=True)
      return
    if raid_time < datetime.now():
      await interaction.response.send_message(":x: **La date est dans le passé**", ephemeral=True)
      return
    template = await db.get_template(template_name, self.user_id)
    if not template:
      await interaction.response.send_message(f":x: **Aucun modèle trouvé nommé `{template_name}`**", ephemeral=True)
      return
    roles = await db.get_template_roles(template_name=template_name, owner_id=self.user_id)
    if not roles:
      await interaction.response.send_message(f":x: **Le modèle `{template_name}` n’a aucun rôle défini, il en faut au moins un**", ephemeral=True)
      return

    msg = await interaction.channel.send(":construction: *Création d'un raid...*")
    raid_id = await db.add_raid(
      leader_id=self.user_id,
      template_name=template_name,
      title=title,
      raid_time=raid_time,
      message_id=msg.id,
      channel_id=msg.channel.id
    )

    embed = await RaidEmbed.create(bot=self.bot, raid_id=raid_id)
    view = await RaidView.create(bot=self.bot, raid_id=raid_id)

    await msg.edit(content="", embed=embed, view=view)
    await interaction.response.send_message(f":white_check_mark: **Raid `{title}` lancé avec succès !**", ephemeral=True)

class RoleModal(ui.Modal):
  def __init__(self, template_name: str, owner_id: int):
    super().__init__(title=f"Ajouter un rôle au modèle `{template_name}`")
    self.template_name = template_name
    self.owner_id = owner_id

    self.role_name_input = ui.InputText(
      label="Nom du rôle",
      placeholder="Ex: Tank, Heal, DPS, etc...",
      required=True,
      max_length=20
    )

    self.emoji_input = ui.InputText(
      label="Emoji (icone du rôle)",
      placeholder="Ex: 🛡️, ⚔️ ou <a:custom:123456>",
      required=True,
      max_length=50
    )

    self.slots_input = ui.InputText(
      label="Nombre de places",
      placeholder="Ex: 5",
      required=True,
      max_length=5
    )

    self.add_item(self.role_name_input)
    self.add_item(self.emoji_input)
    self.add_item(self.slots_input)

  async def callback(self, interaction: Interaction):
    role_name = self.role_name_input.value.strip()
    role_icon = self.emoji_input.value.strip()
    try:
      max_slots = int(self.slots_input.value.strip())
    except ValueError:
      await interaction.response.send_message(":x: **Le nombre de places doit être un entier**", ephemeral=True)
      return
    if max_slots <= 0:
      await interaction.response.send_message(":x: **Le rôle doit avoir au moins une place**", ephemeral=True)
      return
    if not (is_unicode_emoji(role_icon) or is_custom_discord_emoji(role_icon)):
      await interaction.response.send_message(":x: **L'icône n'est pas un emoji valide**", ephemeral=True)
      return

    await db.add_template_role(
      template_name=self.template_name,
      role_name=role_name,
      role_icon=role_icon,
      max_slots=max_slots,
      owner_id=self.owner_id
    )
    await interaction.response.send_message( f":white_check_mark: **Rôle `{role_name}` ajouté au modèle `{self.template_name}`.**", ephemeral=True )

class TemplateModal(ui.Modal):
  def __init__(self, template_name:str, owner_id:int):
    super().__init__(title=f"Modèle `{template_name}`")
    self.template_name = template_name
    self.owner_id = owner_id

    self.description_input = ui.InputText(
      label="Description",
      style=InputTextStyle.long,
      placeholder="Entre ta description ici, le markown marche",
      required=False,
      max_length=1000
    )
    self.url_input = ui.InputText(
      label="(Optionel) Lien du titre",
      style=InputTextStyle.short,
      placeholder="Ex: https://example.com/",
      required=False,
      max_length=500
    )
    self.image_input = ui.InputText(
      label="(Optionel) Lien de l'image",
      style=InputTextStyle.short,
      placeholder="Un lien vers une image en ligne",
      required=False,
      max_length=500
    )
    self.add_item(self.description_input)
    self.add_item(self.image_input)
    self.add_item(self.url_input)

  async def callback(self, interaction: Interaction):
    description = self.description_input.value.strip()
    url = self.url_input.value.strip()
    image = self.image_input.value.strip()

    await db.create_template(template_name=self.template_name, url=url, description=description, image=image, owner_id=self.owner_id)
    await interaction.response.send_message(f":white_check_mark: **Modèle `{self.template_name}` créé avec succès**", ephemeral=True)

class RaidEmbed(Embed):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple, signups:tuple):
    self.bot = bot
    self.raid = raid
    self.template = template
    self.roles = roles
    self.signups = signups

    raid_id, leader_id, template_name, title, raid_time, message_id, channel_id = self.raid
    template_name, url, description, image, owner_id = self.template

    super().__init__(
      colour=Colour.blue(),
      url=url,
      description=description,
      title=f"__**{title.upper()}**__",
      timestamp=datetime.now()
    )

    self.set_footer(text=template_name)
    if image:
      self.set_image(url=image)

  @classmethod
  async def create(cls, bot, raid_id: int):
    raid = await db.get_raid(raid_id)
    raid_id, leader_id, template_name, title, raid_time, message_id, channel_id = raid
    template = await db.get_template(template_name, leader_id)
    roles = await db.get_template_roles(template_name, leader_id)
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
    template_name, url, description, image, owner_id = self.template
    self.add_field(name=f"\u200b", value="", inline=False)
    self.add_field(name=f"<t:{int(raid_timer.timestamp())}:D>", value="")
    self.add_field(name=f"<t:{int(raid_timer.timestamp())}:t>", value="")
    self.add_field(name=f"<t:{int(raid_timer.timestamp())}:R>", value="")
    self.add_field(name=f"\u200b", value="", inline=False)

    total_signed = 0
    max_raid_slots = 0

    for role in self.roles:
      role_name, role_icon, max_slots = role
      role_signups = []

      for signup in self.signups:
        user_id, signup_role_name, signup_time, signup_rank = signup
        if signup_role_name == role_name:
          user_name = f"<@{user_id}>"
          role_signups.append(f"`{signup_rank}` {user_name}")

      total_signed += len(role_signups)
      max_raid_slots += max_slots
      role_signups.sort()
      value = "\n".join(role_signups) or "—"
      value = value + "\n \u200b"
      self.add_field(name=f"{role_icon} {role_name} {len(role_signups)}/{max_slots}", value=value)


    absents = []
    for signup in self.signups:
      user_id, signup_role_name, signup_time, signup_rank = signup
      if signup_role_name == "absent":
        user_name = f"<@{user_id}>"
        absents.append(f"`{signup_rank}` {user_name}")

    value = "\n".join(absents) or "—"
    self.add_field(name=f":no_entry_sign: {len(absents)} Absent" + "" if len(absents)==0 else "s", value=value, inline=False)

    self.insert_field_at(index=4, name=f":busts_in_silhouette: {total_signed}/{max_raid_slots} participants", value="", inline=False)


class RoleSelector(ui.Select):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple):
    self.bot = bot
    self.raid = raid
    self.template = template
    self.roles = roles
    options = [
      SelectOption(label=role_name, emoji=parse_emoji(role_icon), value=role_name)
      for role_name, role_icon, max_slots in self.roles
    ]
    super().__init__(
      placeholder="Choisis un rôle",
      min_values=1,
      max_values=1,
      options=options
    )

  async def callback(self, interaction: Interaction):
    user_id = interaction.user.id
    raid_id, leader_id, template_name, title, raid_time_str, message_id, channel_id = self.raid
    role_name = self.values[0]
    await db.signup_user(user_id=user_id, raid_id=raid_id, role_name=role_name)

    embed = await RaidEmbed.create(self.bot, raid_id)
    view = await RaidView.create(self.bot, raid_id)

    try:
      channel = await self.bot.fetch_channel(channel_id)
      message = await channel.fetch_message(message_id)
      await message.edit(embed=embed, view=view)
    except Exception as e:
      logger.error(f"[!?] Could not update raid message: {e}")
    await interaction.response.send_message(f":white_check_mark: **Tu es inscrit en tant que `{role_name}`**", ephemeral=True)



class AbsenceButton(ui.Button):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple):
    self.bot = bot
    self.raid = raid
    self.template = template
    self.roles = roles
    super().__init__(
      label="Absent",
      emoji="🚫",
      style=ButtonStyle.grey
    )
  async def callback(self, interaction: Interaction):
    user_id = interaction.user.id
    raid_id, leader_id, template_name, title, raid_time_str, message_id, channel_id = self.raid
    await db.signup_user(user_id=user_id, raid_id=raid_id, role_name="absent")

    embed = await RaidEmbed.create(self.bot, raid_id)
    view = await RaidView.create(self.bot, raid_id)

    channel = await self.bot.fetch_channel(channel_id)
    message = await channel.fetch_message(message_id)
    await message.edit(embed=embed, view=view)
    await interaction.response.send_message(f":white_check_mark: **Tu es marqué absent**", ephemeral=True)



class RaidView(ui.View):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple) -> None:
    super().__init__(timeout=None)
    self.add_item(RoleSelector(bot, raid, template, roles))
    self.add_item(AbsenceButton(bot, raid, template, roles))


  @classmethod
  async def create(cls, bot, raid_id: int):
    raid = await db.get_raid(raid_id)
    raid_id, leader_id, template_name, title, raid_time, message_id, channel_id = raid
    template = await db.get_template(template_name, leader_id)
    roles = await db.get_template_roles(template_name, leader_id)

    view = cls(bot, raid, template, roles)
    return view



class Raid(commands.Cog):
  def __init__(self, bot: Bot):
    self.bot = bot
    self.checkuploop.start()

  def cog_unload(self):
    self.checkuploop.cancel()

  @tasks.loop(hours=2)
  async def checkuploop(self):
    messages_infos = await db.clean_expired_raids()
    for message_info in messages_infos:
      message_id, channel_id = message_info
      try:
        channel = await self.bot.fetch_channel(channel_id)
        message = await channel.fetch_message(message_id)
        await message.edit(content="*Ce raid est terminé* :saluting_face:",view=None)
      except Exception as e:
        logger.error(f"[!?] Could not update raid message: {e}")


  @checkuploop.before_loop
  async def before_checkup(self):
    await db.checkup()


  template = SlashCommandGroup(
    name="modele",
    description="Gères et crée des modèle",
    default_member_permissions=Permissions.none()
  )


  # @commands.cooldown(1, 30, commands.BucketType.user)
  @template.command(
    name="creer",
    description="Crée un nouveau modèle avec som nom, sa description etc... (Attention, les modèles sont publics)",
    default_member_permissions=Permissions.none()
  )
  async def create(
    self,
    ctx: ApplicationContext,
    template_name:Option(name="nom", input_type=str, max_length=50, description="Le nom du modèle, utilise quelque chose de simple"),
  ):
    user_id = ctx.user.id
    template = await db.get_template(template_name=template_name, owner_id=user_id)
    if template:
      await ctx.respond(f":warning:  **Tu possèdes déjà un modèle nommé `{template_name}`, supprime le ou change de nom**", ephemeral=True)
      return
    await ctx.send_modal(TemplateModal(template_name=template_name, owner_id=user_id))


  @template.command(
    name="supprimer",
    description="Supprime un modèle",
    default_member_permissions=Permissions.none()
  )
  async def remove(
      self,
      ctx: ApplicationContext,
      template_name:Option(name="nom", input_type=str, description="Nom du modèle à supprimer"),
  ):
    user_id = ctx.user.id
    removed = await db.remove_template(template_name=template_name, owner_id=user_id)
    if removed:
      await ctx.respond(f":wastebasket: **Modèle `{template_name}` supprimé**", ephemeral=True)
    else:
      await ctx.respond(f":x: **Tu ne possède pas de modèle nommé `{template_name}`**", ephemeral=True)


  role = template.create_subgroup(
    "role",
    description="Gères les rôles d'un modèle",
    default_member_permissions=Permissions.none(),
  )

  @role.command(
    name="ajouter",
    description="Ajoute/remplace un rôle à un modèle",
    default_member_permissions=Permissions.none()
  )
  async def add(
    self,
    ctx: ApplicationContext,
    template_name:Option(name="modele", input_type=str, description="Nom du modèle auquel ajouter le rôle"),
  ):
    user_id = ctx.user.id
    template = await db.get_template(template_name=template_name, owner_id=user_id)
    if not template:
      await ctx.respond(f":x: **Modèle `{template_name}` introuvable.**", ephemeral=True)
      return
    await ctx.send_modal(RoleModal(template_name=template_name, owner_id=user_id))


  @role.command(
    name="retirer",
    description="Retire un rôle d'un modèle",
    default_member_permissions=Permissions.none()
  )
  async def remove(
    self,
    ctx: ApplicationContext,
    template_name:Option(name="modele", input_type=str, description="Nom du modèle duquel retirer le rôle"),
    role_name:Option(name="role", input_type=str, description="Nom du rôle"),
  ):
    user_id = ctx.user.id
    removed = await db.remove_template_role(template_name=template_name, role_name=role_name, owner_id=user_id)
    if removed:
      await ctx.respond(f":white_check_mark: **Le rôle `{role_name}` a été retiré au modèle `{template_name}`**", ephemeral=True)
    else:
      await ctx.respond(f":x: **Tu n´as pas de rôle `{role_name}` dans le modèle `{template_name}`**", ephemeral=True)


  raid = SlashCommandGroup(
    "raid",
    description="Manage and start raids",
    default_member_permissions=Permissions.none()
  )

  @guild_only()
  # @commands.cooldown(1, 30, commands.BucketType.user)
  @raid.command(
    name="lancer",
    description="Lance un raid",
    default_member_permissions=Permissions.none()
  )
  async def start(
    self,
    ctx: ApplicationContext,
  ):
    user_id = ctx.user.id
    await ctx.send_modal(RaidModal(self.bot, user_id))

def setup(bot: Bot):
  logger.info("[~~] Loading Raid...")
  bot.add_cog(Raid(bot))
  logger.info("[OK] Raid loaded")
