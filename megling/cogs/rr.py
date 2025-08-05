import discord
from discord.ext import commands
from discord import ApplicationContext, SlashCommandGroup, Bot, ComponentType
from megling.logsetup import setupLogger

logger = setupLogger(__name__)

class SetupModal(discord.ui.Modal):
  def __init__(self, *args, **kwargs) -> None:
    super().__init__(*args, **kwargs)

  async def callback(self, interaction: discord.Interaction):
    embed = discord.Embed(title="Modal Results")
    embed.add_field(name="Short Input", value=self.children[0].value)
    embed.add_field(name="Long Input", value=self.children[1].value)
    await interaction.response.send_message(embeds=[embed])

class RoleMenu(discord.ui.View):
  def __init__(self, roles_list : list[discord.Role], placeholder):
    super().__init__(timeout=None)
    self.roles_list = roles_list
    self.placeholder = placeholder

  @discord.ui.select(
    custom_id="select-menu",
    select_type = ComponentType.role_select,
    placeholder = self.placeholder,
    min_values = 1,
    max_values = 1,
  )
  async def select_callback(self, select, interaction):
    selected_role = select.values[0]
    role = interaction.guild.get_role(int(selected_role.id))
    if role is None:
      await interaction.response.send_message(":interrobang:  **I couldn't find that role**", ephemeral=True)
      return
    try:
      await interaction.user.add_roles(role, reason="Selected via role menu")
      await interaction.response.send_message(f":white_check_mark:  **You were given the {role.name} role!**", ephemeral=True)
    except Exception as e:
      await interaction.response.send_message(f":interrobang:  **An error occurred**", ephemeral=True)
      logger.error(f"[?!] Reaction role failed to asign role: {e}")

class ReactionRole(commands.Cog):
  def __init__(self, bot:Bot):
    self.bot = bot

  rr = SlashCommandGroup("rr", description="Reaction Role commands")

  @rr.command()
  async def setup(self, ctx:ApplicationContext):
    await ctx.send(view=RoleMenu([]))

def setup(bot:Bot):
  logger.info("[~~]Loading Reaction Role...")
  bot.add_cog(ReactionRole(bot))
  logger.info("[OK] Reaction Role loaded")
