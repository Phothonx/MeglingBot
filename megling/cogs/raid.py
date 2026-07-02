"""Raid planner: reusable templates, signup messages, live management, history.

Flow:
    /raid template create <name>  modal for infos, then a builder to add roles
    /raid template edit|delete|list
    /raid start template:<autocomplete> title:<text> when:<time>
        posts the signup message: role select + absent/withdraw buttons and a
        leader-only manage panel (change time/title, ping, kick, cancel)
    when the raid time passes, the message is frozen into a recap embed and
    the raid is archived; /raid history lists a guild's past raids.

The signup view is *persistent*: components carry fixed custom_ids and the
raid is resolved from the message id, so buttons keep working after restarts.
Commands are hidden from regular members by default (admins can grant them to
raid-leader roles in Server Settings > Integrations).
"""

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta

import discord
from discord import (
    ApplicationContext,
    AutocompleteContext,
    Bot,
    ButtonStyle,
    Colour,
    Embed,
    InputTextStyle,
    Interaction,
    InteractionContextType,
    Option,
    PartialEmoji,
    Permissions,
    SelectOption,
    SlashCommandGroup,
    ui,
)
from discord.ext import commands, tasks

from megling.db.raid import ABSENT, RaidDB

logger = logging.getLogger(__name__)

MAX_ROLES = 20  # keeps us clear of Discord's 25-option/25-field limits

# -- Small parsers ---------------------------------------------------------------

CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:\w+:\d+>")
RELATIVE_TIME_PATTERN = re.compile(r"\+(?:(\d+)h)?(?:(\d+)m)?")


def parse_emoji(text: str) -> PartialEmoji | None:
    """Accept a custom discord emoji (<:name:id>) or a unicode emoji."""
    text = text.strip()
    if CUSTOM_EMOJI_PATTERN.fullmatch(text):
        return PartialEmoji.from_str(text)
    if text and all(unicodedata.category(char) in {"So", "Sk", "Cf", "Mn"} for char in text):
        return PartialEmoji(name=text)
    return None


def parse_raid_time(text: str) -> datetime | None:
    """Parse '21:00', '2026-07-05 21:00', '05/07 21:00' or relative '+2h30m'."""
    text = text.strip()
    now = datetime.now()

    match = RELATIVE_TIME_PATTERN.fullmatch(text)
    if match and (match.group(1) or match.group(2)):
        hours, minutes = int(match.group(1) or 0), int(match.group(2) or 0)
        return now + timedelta(hours=hours, minutes=minutes)

    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d/%m %H:%M", "%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%H:%M":  # today, or tomorrow if that time already passed
            parsed = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            if parsed < now:
                parsed += timedelta(days=1)
        elif fmt == "%d/%m %H:%M":  # this year, or next if already passed
            parsed = parsed.replace(year=now.year)
            if parsed < now:
                parsed = parsed.replace(year=now.year + 1)
        return parsed
    return None


# -- Embeds -----------------------------------------------------------------------


def build_raid_embed(raid, roles, signups, *, final: bool = False) -> Embed:
    """The signup message embed; with final=True, the frozen end-of-raid recap."""
    timestamp = int(datetime.fromisoformat(raid["raidTime"]).timestamp())
    header = f"Led by <@{raid['leaderID']}>"
    if raid["description"]:
        header += f"\n\n{raid['description']}"

    embed = Embed(
        title=f"__**{raid['title'].upper()}**__",
        description=header,
        url=raid["url"] or None,
        colour=Colour.dark_grey() if final else Colour.blue(),
    )
    if raid["image"]:
        embed.set_image(url=raid["image"])

    embed.add_field(name=f"<t:{timestamp}:D>", value="")
    embed.add_field(name=f"<t:{timestamp}:t>", value="")
    embed.add_field(name=f"<t:{timestamp}:R>", value="")

    total, capacity = 0, 0
    for role in roles:
        members = [
            f"<@{signup['userID']}>" for signup in signups if signup["roleName"] == role["roleName"]
        ]
        total += len(members)
        capacity += role["maxSlots"]
        embed.add_field(
            name=f"{role['roleIcon']} {role['roleName']}  {len(members)}/{role['maxSlots']}",
            value="\n".join(members) or "—",
        )

    absents = [f"<@{s['userID']}>" for s in signups if s["roleName"] == ABSENT]
    embed.insert_field_at(
        3, name=f":busts_in_silhouette: {total}/{capacity} participants", value="", inline=False
    )
    embed.add_field(
        name=f":no_entry_sign: Absent ({len(absents)})",
        value="\n".join(absents) or "—",
        inline=False,
    )
    embed.set_footer(text="Raid finished" if final else "Sign up with the menu below")
    return embed


def build_template_embed(template, roles) -> Embed:
    """Preview shown in the template builder."""
    embed = Embed(
        title=template["templateName"],
        description=template["description"] or "*No description*",
        url=template["url"] or None,
        colour=Colour.blurple(),
    )
    if template["image"]:
        embed.set_image(url=template["image"])
    for role in roles:
        embed.add_field(
            name=f"{role['roleIcon']} {role['roleName']}",
            value=f"{role['maxSlots']} slot(s)",
        )
    if not roles:
        embed.add_field(name="No roles yet", value="A raid needs at least one role to launch.")
    return embed


async def refresh_raid_message(bot: Bot, db: RaidDB, raid_id: int) -> None:
    """Re-render the signup message after any change to the raid or its signups."""
    raid = await db.get_raid(raid_id)
    if raid is None:
        return
    roles = await db.get_raid_roles(raid_id)
    signups = await db.get_signups(raid_id)
    try:
        channel = bot.get_channel(raid["channelID"]) or await bot.fetch_channel(raid["channelID"])
        message = await channel.fetch_message(raid["messageID"])
        await message.edit(
            embed=build_raid_embed(raid, roles, signups), view=make_signup_view(db, roles)
        )
    except discord.HTTPException:
        logger.exception("Could not refresh the message of raid %s", raid_id)


# -- Signup view (persistent) --------------------------------------------------------


class RaidSignupView(ui.View):
    """Attached to every raid message; also registered once at startup so the
    components keep responding after a bot restart (fixed custom_ids, raid
    resolved from the message id)."""

    def __init__(self, db: RaidDB):
        super().__init__(timeout=None)
        self.db = db

    async def _get_raid(self, interaction: Interaction):
        raid = await self.db.get_raid_by_message(interaction.message.id)
        if raid is None:
            await interaction.response.send_message(
                ":interrobang:  **This raid is no longer active**", ephemeral=True
            )
        return raid

    @ui.select(
        custom_id="raid:signup",
        placeholder="Choose your role",
        min_values=1,
        max_values=1,
        options=[SelectOption(label="placeholder")],  # real options live in the message
    )
    async def signup(self, select: ui.Select, interaction: Interaction):
        raid = await self._get_raid(interaction)
        if raid is None:
            return
        role_name = select.values[0]
        roles = {r["roleName"]: r for r in await self.db.get_raid_roles(raid["raidID"])}
        role = roles.get(role_name)
        if role is None:
            await interaction.response.send_message(
                ":interrobang:  **This role does not exist anymore**", ephemeral=True
            )
            return

        taken = await self.db.count_role_signups(raid["raidID"], role_name)
        signups = await self.db.get_signups(raid["raidID"])
        current = next((s["roleName"] for s in signups if s["userID"] == interaction.user.id), None)
        if current == role_name:
            await interaction.response.send_message(
                f":white_check_mark:  **You are already signed up as `{role_name}`**",
                ephemeral=True,
            )
            return
        if taken >= role["maxSlots"]:
            await interaction.response.send_message(
                f":no_entry:  **`{role_name}` is full ({taken}/{role['maxSlots']})**",
                ephemeral=True,
            )
            return

        await self.db.upsert_signup(raid["raidID"], interaction.user.id, role_name)
        await interaction.response.send_message(
            f":white_check_mark:  **Signed up as `{role_name}`**", ephemeral=True
        )
        await refresh_raid_message(interaction.client, self.db, raid["raidID"])

    @ui.button(label="Absent", emoji="🚫", style=ButtonStyle.grey, custom_id="raid:absent")
    async def absent(self, button: ui.Button, interaction: Interaction):
        raid = await self._get_raid(interaction)
        if raid is None:
            return
        await self.db.upsert_signup(raid["raidID"], interaction.user.id, ABSENT)
        await interaction.response.send_message(
            ":no_entry_sign:  **Marked as absent**", ephemeral=True
        )
        await refresh_raid_message(interaction.client, self.db, raid["raidID"])

    @ui.button(label="Withdraw", emoji="🚪", style=ButtonStyle.grey, custom_id="raid:withdraw")
    async def withdraw(self, button: ui.Button, interaction: Interaction):
        raid = await self._get_raid(interaction)
        if raid is None:
            return
        removed = await self.db.remove_signup(raid["raidID"], interaction.user.id)
        if removed:
            await interaction.response.send_message(
                ":wave:  **You withdrew from the raid**", ephemeral=True
            )
            await refresh_raid_message(interaction.client, self.db, raid["raidID"])
        else:
            await interaction.response.send_message(
                ":interrobang:  **You were not signed up**", ephemeral=True
            )

    @ui.button(label="Manage", emoji="⚙️", style=ButtonStyle.blurple, custom_id="raid:manage")
    async def manage(self, button: ui.Button, interaction: Interaction):
        raid = await self._get_raid(interaction)
        if raid is None:
            return
        is_leader = interaction.user.id == raid["leaderID"]
        if not (is_leader or interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message(
                ":interrobang:  **Only the raid leader can manage this raid**", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f":gear:  **Managing raid `{raid['title']}`**",
            view=RaidManageView(self.db, raid["raidID"]),
            ephemeral=True,
        )


def signup_options(roles) -> list[SelectOption]:
    """Select options for a raid message, built from the raid's role snapshot."""
    return [
        SelectOption(
            label=role["roleName"],
            value=role["roleName"],
            emoji=parse_emoji(role["roleIcon"]),
            description=f"{role['maxSlots']} slot(s)",
        )
        for role in roles
    ]


def make_signup_view(db: RaidDB, roles) -> RaidSignupView:
    """A signup view whose select carries this raid's actual role options."""
    view = RaidSignupView(db)
    view.get_item("raid:signup").options = signup_options(roles)
    return view


# -- Leader management panel (ephemeral) ------------------------------------------------


class EditRaidModal(ui.Modal):
    """Change the title and/or start time of a live raid."""

    def __init__(self, db: RaidDB, raid):
        super().__init__(title=f"Edit raid: {raid['title'][:35]}")
        self.db = db
        self.raid = raid
        self.title_input = ui.InputText(
            label="Title", value=raid["title"], max_length=100, required=True
        )
        self.time_input = ui.InputText(
            label="Start time (21:00, 05/07 21:00, +2h30m)",
            value=raid["raidTime"][:16],
            max_length=30,
            required=True,
        )
        self.add_item(self.title_input)
        self.add_item(self.time_input)

    async def callback(self, interaction: Interaction):
        raid_time = parse_raid_time(self.time_input.value)
        if raid_time is None:
            await interaction.response.send_message(
                ":x:  **Could not parse that time** — try `21:00`, `05/07 21:00` or `+2h`",
                ephemeral=True,
            )
            return
        await self.db.update_raid(
            self.raid["raidID"], title=self.title_input.value.strip(), raid_time=raid_time
        )
        await interaction.response.send_message(
            ":white_check_mark:  **Raid updated**", ephemeral=True
        )
        await refresh_raid_message(interaction.client, self.db, self.raid["raidID"])


class KickSelect(ui.Select):
    def __init__(self, db: RaidDB, raid_id: int, signups, guild: discord.Guild):
        self.db = db
        self.raid_id = raid_id
        options = []
        for signup in signups[:25]:
            member = guild.get_member(signup["userID"])
            label = member.display_name if member else f"Participant #{signup['signupRank']}"
            options.append(SelectOption(label=label, value=str(signup["userID"])))
        super().__init__(placeholder="Kick a participant…", options=options)

    async def callback(self, interaction: Interaction):
        user_id = int(self.values[0])
        await self.db.remove_signup(self.raid_id, user_id)
        await interaction.response.send_message(
            f":boot:  **Removed <@{user_id}> from the raid**", ephemeral=True
        )
        await refresh_raid_message(interaction.client, self.db, self.raid_id)


class RaidManageView(ui.View):
    def __init__(self, db: RaidDB, raid_id: int):
        super().__init__(timeout=600)
        self.db = db
        self.raid_id = raid_id

    @ui.button(label="Edit title / time", emoji="📝", style=ButtonStyle.blurple)
    async def edit(self, button: ui.Button, interaction: Interaction):
        raid = await self.db.get_raid(self.raid_id)
        if raid is None:
            await interaction.response.send_message(
                ":interrobang:  **Raid is gone**", ephemeral=True
            )
            return
        await interaction.response.send_modal(EditRaidModal(self.db, raid))

    @ui.button(label="Ping participants", emoji="📣", style=ButtonStyle.grey)
    async def ping(self, button: ui.Button, interaction: Interaction):
        raid = await self.db.get_raid(self.raid_id)
        signups = await self.db.get_signups(self.raid_id)
        mentions = [f"<@{s['userID']}>" for s in signups if s["roleName"] != ABSENT]
        if raid is None or not mentions:
            await interaction.response.send_message(
                ":interrobang:  **Nobody to ping**", ephemeral=True
            )
            return
        timestamp = int(datetime.fromisoformat(raid["raidTime"]).timestamp())
        await interaction.channel.send(
            f"📣 {' '.join(mentions)} — raid **{raid['title']}** starts <t:{timestamp}:R>!"
        )
        await interaction.response.send_message(":white_check_mark:  **Pinged**", ephemeral=True)

    @ui.button(label="Kick", emoji="👢", style=ButtonStyle.grey)
    async def kick(self, button: ui.Button, interaction: Interaction):
        signups = await self.db.get_signups(self.raid_id)
        if not signups:
            await interaction.response.send_message(
                ":interrobang:  **Nobody signed up yet**", ephemeral=True
            )
            return
        view = ui.View(timeout=300)
        view.add_item(KickSelect(self.db, self.raid_id, signups, interaction.guild))
        await interaction.response.send_message(
            ":boot:  **Pick someone to remove**", view=view, ephemeral=True
        )

    @ui.button(label="Cancel raid", emoji="🗑️", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction):
        raid = await self.db.get_raid(self.raid_id)
        if raid is None:
            await interaction.response.send_message(
                ":interrobang:  **Raid is gone**", ephemeral=True
            )
            return
        try:
            channel = interaction.client.get_channel(raid["channelID"])
            message = await channel.fetch_message(raid["messageID"])
            await message.edit(
                content=f":x:  **Raid `{raid['title']}` was cancelled**", embed=None, view=None
            )
        except (discord.HTTPException, AttributeError):
            logger.exception("Could not edit the message of cancelled raid %s", self.raid_id)
        await self.db.delete_raid(self.raid_id)
        await interaction.response.send_message(":x:  **Raid cancelled**", ephemeral=True)


# -- Template builder ----------------------------------------------------------------


class TemplateInfoModal(ui.Modal):
    """Description / link / image of a template; used at creation and for edits."""

    def __init__(self, db: RaidDB, template_name: str, owner_id: int, existing=None):
        super().__init__(title=f"Template: {template_name[:35]}")
        self.db = db
        self.template_name = template_name
        self.owner_id = owner_id
        self.description_input = ui.InputText(
            label="Description (markdown works)",
            style=InputTextStyle.long,
            value=existing["description"] if existing else None,
            required=False,
            max_length=1000,
        )
        self.url_input = ui.InputText(
            label="Title link (optional)",
            value=existing["url"] if existing else None,
            required=False,
            max_length=500,
        )
        self.image_input = ui.InputText(
            label="Image link (optional)",
            value=existing["image"] if existing else None,
            required=False,
            max_length=500,
        )
        self.add_item(self.description_input)
        self.add_item(self.url_input)
        self.add_item(self.image_input)

    async def callback(self, interaction: Interaction):
        await self.db.create_template(
            self.template_name,
            self.owner_id,
            description=self.description_input.value.strip(),
            url=self.url_input.value.strip(),
            image=self.image_input.value.strip(),
        )
        template = await self.db.get_template(self.template_name, self.owner_id)
        roles = await self.db.get_template_roles(self.template_name, self.owner_id)
        builder = TemplateBuilderView(self.db, self.template_name, self.owner_id)
        embed = build_template_embed(template, roles)
        # Reached either from /raid template create (fresh response) or from the
        # builder's "Edit infos" button (edit the builder message in place).
        if interaction.message:
            await interaction.response.edit_message(embed=embed, view=builder)
        else:
            await interaction.response.send_message(embed=embed, view=builder, ephemeral=True)


class AddRoleModal(ui.Modal):
    def __init__(self, db: RaidDB, template_name: str, owner_id: int):
        super().__init__(title="Add a role")
        self.db = db
        self.template_name = template_name
        self.owner_id = owner_id
        self.name_input = ui.InputText(label="Role name (Tank, Healer…)", max_length=20)
        self.emoji_input = ui.InputText(label="Emoji (🛡️ or <:custom:123>)", max_length=50)
        self.slots_input = ui.InputText(label="Slots", max_length=3, placeholder="5")
        self.add_item(self.name_input)
        self.add_item(self.emoji_input)
        self.add_item(self.slots_input)

    async def callback(self, interaction: Interaction):
        role_name = self.name_input.value.strip()
        icon = self.emoji_input.value.strip()
        try:
            slots = int(self.slots_input.value.strip())
        except ValueError:
            slots = 0
        if slots < 1:
            await interaction.response.send_message(
                ":x:  **Slots must be a positive number**", ephemeral=True
            )
            return
        if parse_emoji(icon) is None:
            await interaction.response.send_message(
                ":x:  **That does not look like a valid emoji**", ephemeral=True
            )
            return

        roles = await self.db.get_template_roles(self.template_name, self.owner_id)
        if len(roles) >= MAX_ROLES and role_name not in [r["roleName"] for r in roles]:
            await interaction.response.send_message(
                f":x:  **A template can have at most {MAX_ROLES} roles**", ephemeral=True
            )
            return

        await self.db.add_template_role(self.template_name, self.owner_id, role_name, icon, slots)
        template = await self.db.get_template(self.template_name, self.owner_id)
        roles = await self.db.get_template_roles(self.template_name, self.owner_id)
        await interaction.response.edit_message(
            embed=build_template_embed(template, roles),
            view=TemplateBuilderView(self.db, self.template_name, self.owner_id),
        )


class RemoveRoleSelect(ui.Select):
    def __init__(self, db: RaidDB, template_name: str, owner_id: int, roles):
        self.db = db
        self.template_name = template_name
        self.owner_id = owner_id
        super().__init__(
            placeholder="Remove a role…",
            options=[
                SelectOption(
                    label=r["roleName"], value=r["roleName"], emoji=parse_emoji(r["roleIcon"])
                )
                for r in roles
            ],
        )

    async def callback(self, interaction: Interaction):
        await self.db.remove_template_role(self.template_name, self.owner_id, self.values[0])
        template = await self.db.get_template(self.template_name, self.owner_id)
        roles = await self.db.get_template_roles(self.template_name, self.owner_id)
        await interaction.response.edit_message(
            embed=build_template_embed(template, roles),
            view=TemplateBuilderView(self.db, self.template_name, self.owner_id),
        )


class TemplateBuilderView(ui.View):
    """Ephemeral editor: live preview embed + add/remove roles + edit infos."""

    def __init__(self, db: RaidDB, template_name: str, owner_id: int, roles=None):
        super().__init__(timeout=600)
        self.db = db
        self.template_name = template_name
        self.owner_id = owner_id
        if roles:
            self.add_item(RemoveRoleSelect(db, template_name, owner_id, roles))

    @classmethod
    async def create(cls, db: RaidDB, template_name: str, owner_id: int):
        roles = await db.get_template_roles(template_name, owner_id)
        return cls(db, template_name, owner_id, roles)

    @ui.button(label="Add role", emoji="➕", style=ButtonStyle.green)
    async def add_role(self, button: ui.Button, interaction: Interaction):
        await interaction.response.send_modal(
            AddRoleModal(self.db, self.template_name, self.owner_id)
        )

    @ui.button(label="Edit infos", emoji="📝", style=ButtonStyle.blurple)
    async def edit_infos(self, button: ui.Button, interaction: Interaction):
        existing = await self.db.get_template(self.template_name, self.owner_id)
        await interaction.response.send_modal(
            TemplateInfoModal(self.db, self.template_name, self.owner_id, existing)
        )

    @ui.button(label="Done", emoji="✅", style=ButtonStyle.grey)
    async def done(self, button: ui.Button, interaction: Interaction):
        await interaction.response.edit_message(
            content=f":white_check_mark:  **Template `{self.template_name}` saved**", view=None
        )


# -- The cog --------------------------------------------------------------------------


async def template_autocomplete(ctx: AutocompleteContext) -> list[str]:
    """Suggest the invoking user's template names."""
    db: RaidDB = ctx.command.cog.db
    names = await db.get_template_names(ctx.interaction.user.id)
    query = (ctx.value or "").lower()
    return [name for name in names if query in name.lower()][:25]


class Raid(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.db = RaidDB()
        bot.add_view(RaidSignupView(self.db))  # revive signup views after restarts
        self.finish_expired.start()

    def cog_unload(self):
        self.finish_expired.cancel()

    # -- End-of-raid recap -------------------------------------------------------

    @tasks.loop(minutes=5)
    async def finish_expired(self):
        for raid in await self.db.expired_raids():
            roles = await self.db.get_raid_roles(raid["raidID"])
            signups = await self.db.get_signups(raid["raidID"])
            recap = build_raid_embed(raid, roles, signups, final=True)
            try:
                channel = self.bot.get_channel(raid["channelID"]) or await self.bot.fetch_channel(
                    raid["channelID"]
                )
                message = await channel.fetch_message(raid["messageID"])
                await message.edit(
                    content=":saluting_face:  **This raid is over**", embed=recap, view=None
                )
            except discord.HTTPException:
                logger.warning("Could not post the recap of raid %s", raid["raidID"])
            await self.db.archive_raid(raid["raidID"])

    @finish_expired.before_loop
    async def prepare(self):
        await self.db.init()
        await self.bot.wait_until_ready()

    # -- Commands ------------------------------------------------------------------

    raid = SlashCommandGroup(
        "raid",
        description="Raid planner",
        default_member_permissions=Permissions.none(),  # admins grant access via Integrations
        contexts={InteractionContextType.guild},
    )
    template = raid.create_subgroup("template", description="Manage your raid templates")

    @template.command(name="create", description="Create a raid template")
    async def template_create(
        self,
        ctx: ApplicationContext,
        name: Option(str, "Template name", max_length=50),
    ):
        if await self.db.get_template(name, ctx.user.id):
            await ctx.respond(
                f":warning:  **You already have a template named `{name}`** — "
                "use `/raid template edit`",
                ephemeral=True,
            )
            return
        await ctx.send_modal(TemplateInfoModal(self.db, name, ctx.user.id))

    @template.command(name="edit", description="Edit a template (infos and roles)")
    async def template_edit(
        self,
        ctx: ApplicationContext,
        name: Option(str, "Template to edit", autocomplete=template_autocomplete),
    ):
        template = await self.db.get_template(name, ctx.user.id)
        if template is None:
            await ctx.respond(f":x:  **No template named `{name}`**", ephemeral=True)
            return
        roles = await self.db.get_template_roles(name, ctx.user.id)
        await ctx.respond(
            embed=build_template_embed(template, roles),
            view=await TemplateBuilderView.create(self.db, name, ctx.user.id),
            ephemeral=True,
        )

    @template.command(name="delete", description="Delete one of your templates")
    async def template_delete(
        self,
        ctx: ApplicationContext,
        name: Option(str, "Template to delete", autocomplete=template_autocomplete),
    ):
        if await self.db.remove_template(name, ctx.user.id):
            await ctx.respond(f":wastebasket:  **Template `{name}` deleted**", ephemeral=True)
        else:
            await ctx.respond(f":x:  **No template named `{name}`**", ephemeral=True)

    @template.command(name="list", description="List your templates")
    async def template_list(self, ctx: ApplicationContext):
        names = await self.db.get_template_names(ctx.user.id)
        if not names:
            await ctx.respond(
                ":shrug:  **No templates yet** — start with `/raid template create`",
                ephemeral=True,
            )
            return
        lines = []
        for name in names:
            roles = await self.db.get_template_roles(name, ctx.user.id)
            icons = " ".join(r["roleIcon"] for r in roles) or "*no roles*"
            lines.append(f"**{name}** — {icons}")
        embed = Embed(
            title="Your raid templates", description="\n".join(lines), colour=Colour.blurple()
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @raid.command(name="start", description="Launch a raid from one of your templates")
    async def start(
        self,
        ctx: ApplicationContext,
        template: Option(str, "Template to use", autocomplete=template_autocomplete),
        title: Option(str, "Raid title", max_length=100),
        when: Option(str, "Start time: 21:00, 05/07 21:00, 2026-07-05 21:00 or +2h30m"),
    ):
        template_row = await self.db.get_template(template, ctx.user.id)
        if template_row is None:
            await ctx.respond(f":x:  **No template named `{template}`**", ephemeral=True)
            return
        roles = await self.db.get_template_roles(template, ctx.user.id)
        if not roles:
            await ctx.respond(
                f":x:  **`{template}` has no roles** — add some with `/raid template edit`",
                ephemeral=True,
            )
            return
        raid_time = parse_raid_time(when)
        if raid_time is None:
            await ctx.respond(
                ":x:  **Could not parse that time** — try `21:00`, `05/07 21:00` or `+2h`",
                ephemeral=True,
            )
            return
        if raid_time < datetime.now():
            await ctx.respond(":x:  **That time is in the past**", ephemeral=True)
            return

        message = await ctx.channel.send(":construction:  *Setting up the raid…*")
        raid_id = await self.db.create_raid(
            guild_id=ctx.guild.id,
            leader_id=ctx.user.id,
            title=title,
            raid_time=raid_time,
            template=template_row,
            roles=roles,
            message_id=message.id,
            channel_id=message.channel.id,
        )
        raid = await self.db.get_raid(raid_id)
        raid_roles = await self.db.get_raid_roles(raid_id)
        await message.edit(
            content="",
            embed=build_raid_embed(raid, raid_roles, []),
            view=make_signup_view(self.db, raid_roles),
        )
        timestamp = int(raid_time.timestamp())
        await ctx.respond(
            f":crossed_swords:  **Raid `{title}` launched — starts <t:{timestamp}:R>**",
            ephemeral=True,
        )

    @raid.command(name="history", description="Recent raids of this server")
    async def history(
        self,
        ctx: ApplicationContext,
        count: Option(int, "How many raids to show", min_value=1, max_value=20, default=10),
    ):
        logs = await self.db.get_history(ctx.guild.id, count)
        if not logs:
            await ctx.respond(":shrug:  **No raid has finished here yet**", ephemeral=True)
            return
        lines = []
        for log in logs:
            timestamp = int(datetime.fromisoformat(log["raidTime"]).timestamp())
            roster = json.loads(log["roster"] or "{}")
            participants = sum(len(v) for k, v in roster.items() if k != ABSENT)
            lines.append(
                f"**{log['title']}** — <t:{timestamp}:D> — "
                f"led by <@{log['leaderID']}> — {participants} participant(s)"
            )
        embed = Embed(
            title=f"Last {len(logs)} raid(s)", description="\n".join(lines), colour=Colour.blue()
        )
        await ctx.respond(embed=embed, ephemeral=True)


def setup(bot: Bot):
    bot.add_cog(Raid(bot))
