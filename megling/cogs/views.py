import discord
import importlib
from discord.ext import commands
from discord import ApplicationContext, SlashCommandGroup, Bot
from megling.logsetup import setupLogger

logger = setupLogger(__name__)

# Custom Select Menu for Roles
class CustomRoleSelect(discord.ui.Select):
  def __init__(self, roles: list[discord.Role], emojis:list[str], placeholder: str):
    options = [
      discord.SelectOption(label=role.name, emoji=emoji, value=str(role.id))
      for role, emoji in zip(roles, emojis)
    ]
    super().__init__(
      # custom_id="custom-role-select",
      placeholder=placeholder,
      min_values=1,
      max_values=len(options),
      options=options
    )

  async def callback(self, interaction: discord.Interaction):
    added_roles = []
    for role_id in self.values:
      role = interaction.guild.get_role(int(role_id))
      if role:
        try:
          await interaction.user.add_roles(role, reason="Selected via role menu")
          added_roles.append(f"<@&{role.id}>")
        except Exception as e:
          logger.error(f"[!] Failed to assign role {role.name}: {e}")

    if added_roles:
      await interaction.response.send_message(f":white_check_mark: Added role(s): {' '.join(added_roles)}", ephemeral=True)


# View that contains the select menu
class RoleMenu(discord.ui.View):
  def __init__(self, roles: list[discord.Role], emojis:list[str], placeholder: str):
    super().__init__(timeout=None)
    self.add_item(CustomRoleSelect(roles, emojis, placeholder))


class Views(commands.Cog):
  def __init__(self, bot: Bot):
    self.bot = bot

    # https://embed.dan.onl/

  views = SlashCommandGroup("views", description="Make views and embeds")

  @views.command(name="setup")
  async def setup2(self, ctx: ApplicationContext, embed_template:str="", view_template:str="", message:str=""):
    if embed_template != "":
      try:
        embed_mod = importlib.import_module(f"..templates.embeds.{embed_template}", package=__package__)
        embed = getattr(embed_mod, "embed", None)
      except Exception as e:
        logger.error(f"[?!] Failed to load embed template: {e}")
        await ctx.respond(f":x: Failed to load embed template", ephemeral=True)
        return
    else:
      embed=None

    if view_template != "":
      try:
        view_mod = importlib.import_module(f"..templates.views.{view_template}", package=__package__)
        View = getattr(view_mod, "View", None)
        view = View()
      except Exception as e:
        logger.error(f"[?!] Failed to load view template: {e}")
        await ctx.respond(f":x: Failed to load view template", ephemeral=True)
        return
    else:
      view=None

    await ctx.channel.send(content=message, embed=embed , view=view)

def setup(bot: Bot):
  logger.info("[~~] Loading Views...")
  bot.add_cog(Views(bot))
  logger.info("[OK] Views loaded")
