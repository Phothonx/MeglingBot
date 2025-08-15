import discord

ROLES = [
  [ "Vert", "🟩", 1385358722645364736],
  [ "Rouge", "🟥", 1385358689648771093]
]

class RoleSelector(discord.ui.Select):
  def __init__(self):
    options = [
      discord.SelectOption(label=role[0], emoji=role[1], value=str(role[2]))
      for role in ROLES
    ]

    super().__init__(
      placeholder="Choose at least one role...",
      min_values=1,
      max_values=len(options),
      options=options
    )

  async def callback(self, interaction: discord.Interaction):
    added_roles = []
    for role_id in self.values:
      role = interaction.guild.get_role(int(role_id))
      if role:
        await interaction.user.add_roles(role, reason="Selected via role menu")
        added_roles.append(f"<@&{role.id}>")

    if added_roles:
      await interaction.response.send_message(f":white_check_mark: Added role(s): {' '.join(added_roles)}", ephemeral=True)


class ResetButton(discord.ui.Button):
  def __init__(self):
    super().__init__(
      label="Reset",
      style=discord.ButtonStyle.red
    )
  async def callback(self, interaction: discord.Interaction):
    for role_id in ROLES:
      role = interaction.guild.get_role(role_id[2])
      if role and role in interaction.user.roles:
        await interaction.user.remove_roles(role)

    await interaction.response.send_message(f":white_check_mark: **All roles where removed**", ephemeral=True)


class View(discord.ui.View):
  def __init__(self):
    super().__init__(timeout=None)
    self.add_item(RoleSelector())
    self.add_item(ResetButton())

view = View()
