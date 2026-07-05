"""Self-role menus: members pick their own roles from a select menu.

    /rolemenu create title: [description] [mode]
        opens an ephemeral builder: pick the roles with Discord's native role
        picker, preview the menu, then publish it to the channel.

The published menu is *stateless*: the configured roles live in the message's
own select options, and the persistent callback reads them back from the
message — no database, nothing breaks on restart, and deleting the message is
all it takes to remove a menu. Selections are synced: whatever a member
submits is exactly the set of menu roles they end up with.

Requires Manage Roles to create menus. The bot can only hand out roles below
its own top role; unmanageable roles are skipped at build time.
"""

import logging

import discord
from discord import (
    ApplicationContext,
    Bot,
    ButtonStyle,
    Colour,
    ComponentType,
    Embed,
    Interaction,
    InteractionContextType,
    Member,
    Option,
    Permissions,
    Role,
    SelectOption,
    SlashCommandGroup,
    ui,
)
from discord.ext import commands

logger = logging.getLogger(__name__)

PICK_ID = "rolemenu:pick"


def assignable(role: Role, me: Member) -> bool:
    """Can the bot safely hand out this role?"""
    return not role.managed and not role.is_default() and role.position < me.top_role.position


def menu_role_ids(message: discord.Message) -> set[int]:
    """Read the configured role ids back from the published select's options."""
    for row in message.components:
        for component in row.children:
            if getattr(component, "custom_id", None) == PICK_ID:
                return {int(option.value) for option in component.options}
    return set()


# -- Published menu (persistent, stateless) ---------------------------------------


class RoleMenuView(ui.View):
    """Registered once at startup; serves every published menu message."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.select(
        custom_id=PICK_ID,
        placeholder="Pick your roles",
        min_values=0,
        options=[SelectOption(label="placeholder")],  # real options live in the message
    )
    async def pick(self, select: ui.Select, interaction: Interaction):
        member = interaction.user
        guild = interaction.guild
        chosen = {int(value) for value in select.values}
        configured = menu_role_ids(interaction.message)

        to_add, to_remove = [], []
        for role_id in configured:
            role = guild.get_role(role_id)
            if role is None or not assignable(role, guild.me):
                continue
            has_role = role in member.roles
            if role_id in chosen and not has_role:
                to_add.append(role)
            elif role_id not in chosen and has_role:
                to_remove.append(role)

        try:
            if to_add:
                await member.add_roles(*to_add, reason="Role menu")
            if to_remove:
                await member.remove_roles(*to_remove, reason="Role menu")
        except discord.Forbidden:
            await interaction.response.send_message(
                ":x:  **I am missing permissions to manage these roles**", ephemeral=True
            )
            return

        parts = []
        if to_add:
            parts.append("added " + " ".join(role.mention for role in to_add))
        if to_remove:
            parts.append("removed " + " ".join(role.mention for role in to_remove))
        summary = " and ".join(parts) or "no changes"
        await interaction.response.send_message(
            f":white_check_mark:  **Roles updated:** {summary}", ephemeral=True
        )


def build_menu_message(title: str, description: str, roles: list[Role], single: bool):
    """The embed + select posted to the channel."""
    embed = Embed(
        title=title,
        description=description or "Use the menu below to pick your roles.",
        colour=Colour.blurple(),
    )
    embed.add_field(name="Available roles", value="\n".join(r.mention for r in roles))

    view = RoleMenuView()
    select = view.get_item(PICK_ID)
    select.options = [SelectOption(label=role.name, value=str(role.id)) for role in roles]
    select.max_values = 1 if single else len(select.options)
    return embed, view


# -- Builder (ephemeral) -------------------------------------------------------------


class MenuBuilderView(ui.View):
    def __init__(self, title: str, description: str, single: bool):
        super().__init__(timeout=600)
        self.menu_title = title
        self.description = description
        self.single = single
        self.roles: list[Role] = []
        self.skipped: list[Role] = []

    def preview(self) -> Embed:
        embed = Embed(
            title=f"Building: {self.menu_title}",
            description=self.description or "*No description*",
            colour=Colour.dark_grey(),
        )
        embed.add_field(
            name=f"Roles ({len(self.roles)}/25)",
            value="\n".join(role.mention for role in self.roles) or "*Pick roles below*",
        )
        if self.skipped:
            embed.add_field(
                name=":warning: Skipped (I can't assign these)",
                value="\n".join(role.mention for role in self.skipped),
                inline=False,
            )
        mode = "Single choice" if self.single else "Multiple choices"
        embed.set_footer(
            text=f"{mode} — type in the picker to search; pick again to add more roles"
        )
        return embed

    @ui.select(
        select_type=ComponentType.role_select,
        placeholder="Add roles to the menu…",
        min_values=1,
        max_values=25,
    )
    async def pick_roles(self, select: ui.Select, interaction: Interaction):
        # Selections accumulate: the picker only displays a couple dozen roles
        # at once, so bigger menus are built by searching and picking in batches.
        me = interaction.guild.me
        for role in select.values:
            if not assignable(role, me):
                if role not in self.skipped:
                    self.skipped.append(role)
            elif role not in self.roles and len(self.roles) < 25:
                self.roles.append(role)  # published select caps at 25 options
        await interaction.response.edit_message(embed=self.preview(), view=self)

    @ui.button(label="Remove all roles", emoji="♻️", style=ButtonStyle.grey)
    async def reset_roles(self, button: ui.Button, interaction: Interaction):
        self.roles.clear()
        self.skipped.clear()
        await interaction.response.edit_message(embed=self.preview(), view=self)

    @ui.button(label="Publish", emoji="📤", style=ButtonStyle.green)
    async def publish(self, button: ui.Button, interaction: Interaction):
        if not self.roles:
            await interaction.response.send_message(
                ":x:  **Pick at least one role first**", ephemeral=True
            )
            return
        embed, view = build_menu_message(self.menu_title, self.description, self.roles, self.single)
        try:
            await interaction.channel.send(embed=embed, view=view)
        except discord.HTTPException:
            await interaction.response.send_message(
                ":x:  **I could not post in this channel**", ephemeral=True
            )
            return
        logger.info(
            "Role menu %r published in guild %s with %d role(s)",
            self.menu_title,
            interaction.guild.id,
            len(self.roles),
        )
        # The menu is posted; make the ephemeral builder disappear.
        await interaction.response.defer()
        await interaction.delete_original_response()

    @ui.button(label="Cancel", emoji="🗑️", style=ButtonStyle.grey)
    async def cancel(self, button: ui.Button, interaction: Interaction):
        await interaction.response.defer()
        await interaction.delete_original_response()


# -- The cog ---------------------------------------------------------------------------


class RoleMenu(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        bot.add_view(RoleMenuView())  # revive published menus after restarts

    rolemenu = SlashCommandGroup(
        "rolemenu",
        description="Self-role menus",
        default_member_permissions=Permissions(manage_roles=True),
        contexts={InteractionContextType.guild},
    )

    @rolemenu.command(name="create", description="Build and publish a self-role menu")
    async def create(
        self,
        ctx: ApplicationContext,
        title: Option(str, "Menu title", max_length=100),
        description: Option(str, "Text shown above the menu", required=False, default=""),
        mode: Option(
            str,
            "Can members hold several of these roles at once?",
            choices=["multiple", "single"],
            default="multiple",
        ),
    ):
        builder = MenuBuilderView(title, description, single=(mode == "single"))
        await ctx.respond(embed=builder.preview(), view=builder, ephemeral=True)


def setup(bot: Bot):
    bot.add_cog(RoleMenu(bot))
