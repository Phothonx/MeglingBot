from typing import Literal
import re
from datetime import datetime

from megling.cogs.raidDBManager import RaidDB
from megling.logsetup import setupLogger

from discord import ApplicationContext, SlashCommandGroup, Bot, ui, Embed, Colour, Permissions, SelectOption, Interaction, ButtonStyle, Option, guild_only, PartialEmoji
from discord.ext import commands, tasks
from discord.ext.commands import CheckFailure

logger = setupLogger(__name__)
db = RaidDB()


CUSTOM_EMOJI_PATTERN = re.compile(r"^<a?:\w+:\d+>$")
def is_custom_discord_emoji(s: str) -> bool:
    return bool(CUSTOM_EMOJI_PATTERN.fullmatch(s.strip()))


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
      title=f"__**{title.upper()}**__",
      timestamp=datetime.now()
    )

    self.set_footer(text=template_name)
    if image:
      self.set_image(url=image)
    # if thumbnail: # TODO enlever thumbnail
    #   self.set_thumbnail(url=thumbnail)

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
    template_name, url, description, image, thumbnail, owner_id = self.template
    self.add_field(name=f"\u200b", value="", inline=False)
    self.add_field(name=f"<t:{int(raid_timer.timestamp())}:D>", value="")
    self.add_field(name=f"<t:{int(raid_timer.timestamp())}:t>", value="")
    self.add_field(name=f"<t:{int(raid_timer.timestamp())}:R>", value="")
    self.add_field(name=f"\u200b", value="", inline=False)
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
      value = value + "\n\u200b"
      self.add_field(name=f"{role_icon} {role_name} {len(role_signups)}/{max_slots}", value=value)

    self.insert_field_at(index=5, name=f":busts_in_silhouette: {total_signed}/{max_raid_slots} participants", value=f"", inline=False)

# maybe add caching to get templates and roles to avoid useless requests, too lazy, will never happen

class RoleSelector(ui.Select):
  def __init__(self, bot:Bot, raid:tuple, template:tuple, roles:tuple):
    self.bot = bot
    self.raid = raid
    self.template = template
    self.roles = roles
    options = [
      SelectOption(label=role_name,  value=role_name) # TODO # emoji=PartialEmoji.from_str(role_icon),
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
      # emoji=PartialEmoji.from_str("<:no_entry_sign:>"), # TODO
      style=ButtonStyle.red
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

  @tasks.loop(hours=24)
  async def checkuploop(self):
    await db.checkup()

  @checkuploop.before_loop
  async def before_checkup(self):
    await self.bot.wait_until_ready()


  template = SlashCommandGroup(
    name="modele",
    description="Gères et crée des modèle",
    default_member_permissions=Permissions.none()
  )


  @template.command(
    name="creer",
    description="Crée un nouveau modèle avec som nom, sa description etc... (Attention, les modèles sont publics)",
    default_member_permissions=Permissions.none()
  )
  async def create(
    self,
    ctx: ApplicationContext,
    template_name:Option(name="nom", input_type=str, description="Le nom du modèle, utilise quelque chose de simple"),
    url:Option(name="lien", input_type=str|None, default=None, required=False, description="(Optionel) Un hyperlien dans le titre de l'embed"),
    description:Option(name="description", input_type=str|None,  default=None, required=False,description="(Optionel) Les infos/directives pour ton raid (Le markdown marche)"),
    image:Option(name="image", input_type=str|None, default=None, required=False, description="(Optionel) Lien vers une image insérée en bas de l'embed"),
    thumbnail:Option(name="miniature", input_type=str|None, default=None, required=False, description="(Optionel) Lien vers une petite image insérée en haut à gauche de l'embed"),
  ):
    user_id = ctx.user.id
    template = await db.get_template(template_name=template_name, owner_id=user_id)
    if template:
      await ctx.respond(f":warning:  **Tu possèdes déjà un modèle nommé `{template_name}`, supprime le ou change de nom**", ephemeral=True)
      return
    await db.create_template(template_name=template_name, url=url, description=description, image=image, thumbnail=thumbnail, owner_id=user_id)
    await ctx.respond(f":white_check_mark: **Modèle `{template_name}` créé avec succès**", ephemeral=True)


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
    role_name:Option(name="nom", input_type=str, description="Nom du rôle"),
    role_icon:Option(name="icone", input_type=str, description="L'icone du rôle (un emoji discord)"),
    max_slots:Option(name="places", input_type=int, description="Le nombre de places pour ce rôle"),
  ):
    max_slots = int(max_slots) # TODO
    if max_slots <= 0:
      await ctx.respond(f":x: **Le rôle doit avoir au moins une place**", ephemeral=True)
      return
    if False: # not is_custom_discord_emoji(role_icon): # TODO
      await ctx.respond(f":x: **L'icone du rôle n'est pas un emoji**", ephemeral=True)
      return
    user_id = ctx.user.id
    template = await db.get_template(template_name=template_name, owner_id=user_id)
    if template:
      await db.add_template_role(template_name=template_name, role_name=role_name, role_icon=role_icon, max_slots=max_slots, owner_id=user_id)
      await ctx.respond(f":white_check_mark: **Le rôle `{role_name}` a été ajouté au modèle `{template_name}`**", ephemeral=True)
    else:
      await ctx.respond(f":x: **Tu ne possède pas de modèle nommé `{template_name}`**", ephemeral=True)


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
  @commands.cooldown(1, 30, commands.BucketType.user)
  @raid.command(
    name="lancer",
    description="Lance un raid",
    default_member_permissions=Permissions.none()
  )
  async def start(
    self,
    ctx: ApplicationContext,
    template_name:Option(name="modele", input_type=str, description="Nom du modèle à utiliser"), title:Option(name="titre", input_type=str, description="Titre du template (convertit en capitales)"),
    user_raid_time:Option(name="horaire", input_type=str, description="Date et horaire de début du raid, format ISO 8601: YYYY-mm-dd HH:MM")
  ):
    await ctx.defer()
    user_id = ctx.user.id
    try:
      raid_time = datetime.strptime(user_raid_time, "%Y-%m-%d %H:%M")
    except ValueError:
      await ctx.respond(f":x: **La date n'est pas au format ISO 8601**", ephemeral=True)
      return
    if raid_time < datetime.utcnow(): # TODO marche pas
      await ctx.respond(":x: **T'es dans le passé là...**", ephemeral=True)
      return
    template = await db.get_template(template_name, user_id)
    if not template:
      await ctx.respond(f":x: **Aucun modèle trouvé nommé `{template_name}`**", ephemeral=True)
      return
    msg = await ctx.channel.send(":construction: *making raid...*")
    raid_id = await db.add_raid(leader_id=user_id, template_name=template_name, title=title, raid_time=raid_time, message_id=msg.id, channel_id=msg.channel.id)
    embed = await RaidEmbed.create(bot=self.bot, raid_id=raid_id)
    view = await RaidView.create(bot=self.bot, raid_id=raid_id)
    await msg.edit(content="", embed=embed, view=view)


def setup(bot: Bot):
  logger.info("[~~] Loading Raid...")
  bot.add_cog(Raid(bot))
  logger.info("[OK] Raid loaded")
