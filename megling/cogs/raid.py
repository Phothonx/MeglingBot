"""Raid planner: reusable templates, signup messages, live management, history.

Flow:
    /raid template create <name>  modal for infos, then a builder to add roles
    /raid template edit|delete|list
    /raid start template:<autocomplete> title:<text> when:<time>
        posts the signup message: role select + absent button and a
        leader-only manage panel (change time/title, ping, kick, cancel)

Lifecycle: when the start time arrives, signups are disabled and the
participants + leader get pinged with a ⚔️ Start button. The leader can still
postpone (signups reopen, the ping resets) — or press Start, which freezes
the message into a recap, archives the raid and removes all interactions.
Raids left pending for 24h are archived automatically. /raid history lists
a guild's past raids.

The signup view is *persistent*: components carry fixed custom_ids and the
raid is resolved from the message id, so buttons keep working after restarts.
Commands are hidden from regular members by default (admins can grant them to
raid-leader roles in Server Settings > Integrations).
"""

import json
import logging
import re
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
    Permissions,
    SelectOption,
    SlashCommandGroup,
    ui,
)
from discord.ext import commands, tasks

from megling.db.raid import ABSENT, RaidDB
from megling.utils import parse_emoji, valid_url

logger = logging.getLogger(__name__)

MAX_ROLES = 20  # keeps us clear of Discord's 25-option/25-field limits

RELATIVE_TIME_PATTERN = re.compile(r"\+(?:(\d+)h)?(?:(\d+)m)?")


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


def raid_is_due(raid) -> bool:
    """Has the raid's start time passed?"""
    return datetime.fromisoformat(raid["raidTime"]) <= datetime.now()


def build_raid_embed(raid, roles, signups, *, final: bool = False, pending: bool = False) -> Embed:
    """The signup message embed. `pending` = start time reached, waiting for the
    leader to press Start; `final` = the frozen end-of-raid recap."""
    timestamp = int(datetime.fromisoformat(raid["raidTime"]).timestamp())
    header = f"Led by <@{raid['leaderID']}>"
    if raid["description"]:
        header += f"\n\n{raid['description']}"

    embed = Embed(
        title=f"__**{raid['title'].upper()}**__",
        description=header,
        url=raid["url"] if valid_url(raid["url"]) else None,
        colour=Colour.dark_grey() if final else Colour.blue(),
    )
    if valid_url(raid["image"]):
        embed.set_image(url=raid["image"])

    embed.add_field(name=f"<t:{timestamp}:D>", value="")
    embed.add_field(name=f"<t:{timestamp}:t>", value="")
    embed.add_field(name=f"<t:{timestamp}:R>", value="")

    total, capacity = 0, 0
    for role in roles:
        members = [
            f"`{signup['signupRank']}` <@{signup['userID']}>"
            for signup in signups
            if signup["roleName"] == role["roleName"]
        ]
        total += len(members)
        capacity += role["maxSlots"]
        embed.add_field(
            name=f"{role['roleIcon']} {role['roleName']}  {len(members)}/{role['maxSlots']}",
            value="\n".join(members) or "—",
        )

    absents = [f"`{s['signupRank']}` <@{s['userID']}>" for s in signups if s["roleName"] == ABSENT]
    embed.insert_field_at(
        3, name=f":busts_in_silhouette: {total}/{capacity} participants", value="", inline=False
    )
    embed.add_field(
        name=f":no_entry_sign: Absent ({len(absents)})",
        value="\n".join(absents) or "—",
        inline=False,
    )
    if final:
        footer = "Raid finished"
    elif pending:
        footer = "Signups closed — waiting for the leader to start the raid"
    else:
        footer = "Sign up with the menu below"
    embed.set_footer(text=footer)
    return embed


def build_template_embed(template, roles) -> Embed:
    """Preview shown in the template builder."""
    embed = Embed(
        title=template["templateName"],
        description=template["description"] or "*No description*",
        url=template["url"] if valid_url(template["url"]) else None,
        colour=Colour.blurple(),
    )
    if valid_url(template["image"]):
        embed.set_image(url=template["image"])
    for role in roles:
        embed.add_field(
            name=f"{role['roleIcon']} {role['roleName']}",
            value=f"{role['maxSlots']} slot(s)",
        )
    if not roles:
        embed.add_field(name="No roles yet", value="A raid needs at least one role to launch.")
    return embed


async def render_raid(db: RaidDB, raid_id: int) -> tuple[Embed, "RaidSignupView"] | None:
    """Current embed + view of a raid; signups are disabled once the start time passed."""
    raid = await db.get_raid(raid_id)
    if raid is None:
        return None
    roles = await db.get_raid_roles(raid_id)
    signups = await db.get_signups(raid_id)
    due = raid_is_due(raid)
    embed = build_raid_embed(raid, roles, signups, pending=due)
    view = make_signup_view(db, roles, disabled=due)
    return embed, view


async def refresh_raid_message(bot: Bot, db: RaidDB, raid_id: int) -> None:
    """Re-render the signup message after any change to the raid or its signups."""
    raid = await db.get_raid(raid_id)
    rendered = await render_raid(db, raid_id)
    if raid is None or rendered is None:
        return
    try:
        channel = bot.get_channel(raid["channelID"]) or await bot.fetch_channel(raid["channelID"])
        message = await channel.fetch_message(raid["messageID"])
        await message.edit(embed=rendered[0], view=rendered[1])
    except discord.HTTPException:
        logger.exception("Could not refresh the message of raid %s", raid_id)


async def finalize_raid(bot: Bot, db: RaidDB, raid_id: int, *, edit_ping: bool = True) -> None:
    """Freeze the signup message into the recap, drop the ping's button, archive."""
    raid = await db.get_raid(raid_id)
    if raid is None:
        return
    roles = await db.get_raid_roles(raid_id)
    signups = await db.get_signups(raid_id)
    recap = build_raid_embed(raid, roles, signups, final=True)

    channel = bot.get_channel(raid["channelID"])
    try:
        channel = channel or await bot.fetch_channel(raid["channelID"])
        message = await channel.fetch_message(raid["messageID"])
        await message.edit(
            content=":crossed_swords:  **This raid has started**", embed=recap, view=None
        )
    except discord.HTTPException:
        logger.warning("Could not post the recap of raid %s", raid_id)

    if edit_ping and raid["pingMessageID"] and channel:
        try:
            ping = await channel.fetch_message(raid["pingMessageID"])
            await ping.edit(view=None)
        except discord.HTTPException:
            pass  # ping message was deleted, nothing to disable

    await db.archive_raid(raid_id)


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
        if raid_is_due(raid):
            await interaction.response.send_message(
                ":no_entry:  **Signups are closed — the raid is about to start**", ephemeral=True
            )
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
        if current != role_name and taken >= role["maxSlots"]:
            await interaction.response.send_message(
                f":no_entry:  **`{role_name}` is full ({taken}/{role['maxSlots']})**",
                ephemeral=True,
            )
            return

        await self.db.upsert_signup(raid["raidID"], interaction.user.id, role_name)
        rendered = await render_raid(self.db, raid["raidID"])
        # Updating the raid message *is* the interaction response: no extra message.
        await interaction.response.edit_message(embed=rendered[0], view=rendered[1])

    @ui.button(label="Absent", emoji="🚫", style=ButtonStyle.grey, custom_id="raid:absent")
    async def absent(self, button: ui.Button, interaction: Interaction):
        raid = await self._get_raid(interaction)
        if raid is None:
            return
        if raid_is_due(raid):
            await interaction.response.send_message(
                ":no_entry:  **Signups are closed — the raid is about to start**", ephemeral=True
            )
            return
        await self.db.upsert_signup(raid["raidID"], interaction.user.id, ABSENT)
        rendered = await render_raid(self.db, raid["raidID"])
        await interaction.response.edit_message(embed=rendered[0], view=rendered[1])

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


def make_signup_view(db: RaidDB, roles, *, disabled: bool = False) -> RaidSignupView:
    """A signup view whose select carries this raid's actual role options.
    `disabled` greys out signing up (start time reached); Manage stays active."""
    view = RaidSignupView(db)
    select = view.get_item("raid:signup")
    select.options = signup_options(roles)
    select.disabled = disabled
    view.get_item("raid:absent").disabled = disabled
    return view


class StartRaidView(ui.View):
    """The ⚔️ button on the start-ping message; persistent like the signup view."""

    def __init__(self, db: RaidDB):
        super().__init__(timeout=None)
        self.db = db

    @ui.button(label="Start the raid", emoji="⚔️", style=ButtonStyle.green, custom_id="raid:begin")
    async def begin(self, button: ui.Button, interaction: Interaction):
        raid = await self.db.get_raid_by_ping_message(interaction.message.id)
        if raid is None:
            # postponed or cancelled: drop the stale button
            await interaction.response.edit_message(view=None)
            return
        is_leader = interaction.user.id == raid["leaderID"]
        if not (is_leader or interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message(
                ":interrobang:  **Only the raid leader can start the raid**", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=f":crossed_swords:  **Raid `{raid['title']}` has started — good luck!**",
            view=None,
        )
        await finalize_raid(interaction.client, self.db, raid["raidID"], edit_ping=False)


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
        if raid_time < datetime.now():
            await interaction.response.send_message(
                ":x:  **That time is in the past**", ephemeral=True
            )
            return
        await self.db.update_raid(
            self.raid["raidID"], title=self.title_input.value.strip(), raid_time=raid_time
        )

        # Postponed after the start ping went out: retract it so signups reopen
        # and a fresh ping fires at the new time.
        if self.raid["pingMessageID"]:
            try:
                channel = interaction.client.get_channel(self.raid["channelID"])
                ping = await channel.fetch_message(self.raid["pingMessageID"])
                await ping.delete()
            except (discord.HTTPException, AttributeError):
                pass
            await self.db.set_ping_message(self.raid["raidID"], None)

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
        channel = interaction.client.get_channel(raid["channelID"])
        try:
            message = await channel.fetch_message(raid["messageID"])
            await message.edit(
                content=f":x:  **Raid `{raid['title']}` was cancelled**", embed=None, view=None
            )
        except (discord.HTTPException, AttributeError):
            logger.exception("Could not edit the message of cancelled raid %s", self.raid_id)
        if raid["pingMessageID"] and channel:
            try:
                ping = await channel.fetch_message(raid["pingMessageID"])
                await ping.delete()
            except discord.HTTPException:
                pass
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
        url = (self.url_input.value or "").strip()
        image = (self.image_input.value or "").strip()
        for label, link in (("title link", url), ("image link", image)):
            if link and not valid_url(link):
                await interaction.response.send_message(
                    f":x:  **The {label} is not a valid URL** — it must start with"
                    " `http://` or `https://`",
                    ephemeral=True,
                )
                return

        await self.db.create_template(
            self.template_name,
            self.owner_id,
            description=self.description_input.value.strip(),
            url=url,
            image=image,
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
        self.emoji_input = ui.InputText(label="Emoji (🛡️, :shield: or <:custom:123>)", max_length=50)
        self.slots_input = ui.InputText(label="Slots", max_length=3, placeholder="5")
        self.add_item(self.name_input)
        self.add_item(self.emoji_input)
        self.add_item(self.slots_input)

    async def callback(self, interaction: Interaction):
        role_name = self.name_input.value.strip()
        try:
            slots = int(self.slots_input.value.strip())
        except ValueError:
            slots = 0
        if slots < 1:
            await interaction.response.send_message(
                ":x:  **Slots must be a positive number**", ephemeral=True
            )
            return
        parsed = parse_emoji(self.emoji_input.value)
        if parsed is None:
            await interaction.response.send_message(
                ":x:  **That does not look like a valid emoji** — paste an emoji,"
                " a `:shortcode:` or a custom `<:name:id>`",
                ephemeral=True,
            )
            return
        icon = str(parsed)  # normalized: :red_square: is stored as 🟥

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
        # revive the signup and start-ping views after restarts
        bot.add_view(RaidSignupView(self.db))
        bot.add_view(StartRaidView(self.db))
        self.lifecycle_tick.start()

    def cog_unload(self):
        self.lifecycle_tick.cancel()

    # -- Lifecycle: open -> pending (ping + Start button) -> started/archived ------

    @tasks.loop(minutes=5)
    async def lifecycle_tick(self):
        for raid in await self.db.due_raids():
            try:  # one broken raid must not stop the loop (task loops die on errors)
                if raid["pingMessageID"] is None:
                    await self._announce_start(raid)
                elif datetime.fromisoformat(raid["raidTime"]) < datetime.now() - timedelta(
                    hours=24
                ):
                    logger.info("Raid %s was never started — auto-archiving", raid["raidID"])
                    await finalize_raid(self.bot, self.db, raid["raidID"])
            except Exception:
                logger.exception("Lifecycle handling failed for raid %s", raid["raidID"])

    async def _announce_start(self, raid) -> None:
        """Start time reached: close signups and ping everyone with a Start button."""
        raid_id = raid["raidID"]
        await refresh_raid_message(self.bot, self.db, raid_id)  # renders disabled
        signups = await self.db.get_signups(raid_id)
        mentions = [f"<@{s['userID']}>" for s in signups if s["roleName"] != ABSENT]
        leader = f"<@{raid['leaderID']}>"
        if leader in mentions:
            mentions.remove(leader)
        try:
            channel = self.bot.get_channel(raid["channelID"]) or await self.bot.fetch_channel(
                raid["channelID"]
            )
            ping = await channel.send(
                f"📣 {' '.join(mentions) or 'Raid time!'} — **{raid['title']}** is due to start!"
                f" {leader}, press the button when everyone is ready.",
                view=StartRaidView(self.db),
            )
        except discord.HTTPException:
            logger.exception("Could not announce the start of raid %s", raid_id)
            return
        await self.db.set_ping_message(raid_id, ping.id)
        logger.info("Raid %s is pending start", raid_id)

    @lifecycle_tick.before_loop
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

        # The raid message is the only output: acknowledge the command silently,
        # post the raid as a plain channel message, then drop the "thinking…" stub.
        await ctx.defer()
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
        await ctx.delete()

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
