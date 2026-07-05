"""Balances: a per-member currency, scoped to each server.

    /balance show [member]      everyone: check a balance
    /balance top [count]        everyone: the guild leaderboard
    /balance give member amount everyone: give some of your own balance away
    /balance edit amount:       banker role: +500, -500, +30%, -30%
                                (omit `member` to pick several members at once)
    /balance set member amount  banker role: exact value, may be negative
    /balance log [member]       banker role: recent transactions
    /balance config role:       staff: choose the banker role

Only the configured banker role (see /balance config) can add or remove
currency; staff (Manage Server) always can. Balances may go negative (debt),
except through /balance give, which requires sufficient funds. Every change
is logged.
"""

import logging
import re
from datetime import UTC, datetime

import discord
from discord import (
    ApplicationContext,
    Bot,
    Colour,
    ComponentType,
    Embed,
    Interaction,
    InteractionContextType,
    Member,
    Option,
    Role,
    SlashCommandGroup,
    ui,
)
from discord.ext import commands

from megling.db.balance import BalanceDB

logger = logging.getLogger(__name__)

COIN = "🪙"


def diff_block(before: int, delta: int, after: int) -> str:
    """A balance change as a diff code block (the +/- lines get colored)."""
    return f"```diff\n{before}\n{delta:+d}\n----------\n{after}\n```"


def change_embed(results: list, reason: str | None, expression: str | None = None) -> Embed:
    """The public embed for banker balance changes.

    `results` holds (member, before, after) tuples; a single member gets the
    full diff block, several get compact `before → after` lines.
    """
    if len(results) == 1:
        member, before, after = results[0]
        description = f"{member.mention}\n{diff_block(before, after - before, after)}"
        title = f"{COIN} Balance updated"
    else:
        description = "\n".join(
            f"`{before} → {after}`  {member.mention}" for member, before, after in results
        )
        title = (
            f"{COIN} Balances updated (`{expression}`)"
            if expression
            else f"{COIN} Balances updated"
        )
    embed = Embed(title=title, description=description, colour=Colour.gold())
    if reason:
        embed.set_footer(text=f"Reason: {reason}")
    return embed


AMOUNT_PATTERN = re.compile(r"([+-]?)(\d+)(%?)")


def apply_amount(current: int, expression: str) -> int | None:
    """Evaluate an adjust expression against a balance; None if it doesn't parse.

    +500 / 500 -> add 500        -500 -> remove 500
    +30% / 30% -> add 30% of it  -30% -> remove 30% of it
    (exact values are /balance set — a bare number here means adding)
    """
    match = AMOUNT_PATTERN.fullmatch(expression.strip())
    if match is None:
        return None
    sign, digits, percent = match.groups()
    value = int(digits)
    if percent:
        value = round(current * value / 100)
    return current - value if sign == "-" else current + value


class NotBanker(commands.CheckFailure):
    """Invoker lacks the guild's configured banker role."""

    def __init__(self, role_id: int | None):
        super().__init__()
        self.role_id = role_id


def is_banker():
    """Allow the guild's banker role (see /balance config) and server staff."""

    async def predicate(ctx: ApplicationContext) -> bool:
        if ctx.user.guild_permissions.manage_guild:
            return True
        role_id = await ctx.command.cog.db.get_banker_role(ctx.guild.id)
        if role_id and any(role.id == role_id for role in ctx.user.roles):
            return True
        raise NotBanker(role_id)

    return commands.check(predicate)


class BulkEditView(ui.View):
    """Ephemeral member picker for /balance edit without a `member` option."""

    def __init__(self, cog, expression: str, reason: str | None):
        super().__init__(timeout=300)
        self.cog = cog
        self.expression = expression
        self.reason = reason

    @ui.select(
        select_type=ComponentType.user_select,
        placeholder="Pick one or more members…",
        min_values=1,
        max_values=25,
    )
    async def pick(self, select: ui.Select, interaction: Interaction):
        members = [member for member in select.values if not member.bot]
        if not members:
            await interaction.response.send_message(
                ":interrobang:  **Bots have no use for money**", ephemeral=True
            )
            return
        embed = await self.cog._edit_members(
            interaction.guild.id, members, self.expression, interaction.user.id, self.reason
        )
        # The picker was ephemeral, so the result wouldn't show who did it:
        # name the banker on the embed itself.
        embed.set_author(name=f"By {interaction.user.display_name}")
        try:
            await interaction.channel.send(embed=embed)
        except discord.HTTPException:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.edit_message(
            content=f":white_check_mark:  **Applied to {len(members)} member(s)**", view=None
        )


class Balance(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.db = BalanceDB()
        bot.loop.create_task(self.db.init())

    balance = SlashCommandGroup(
        "balance",
        description="Member balances",
        contexts={InteractionContextType.guild},
    )

    # -- Open to everyone ------------------------------------------------------

    @balance.command(name="show", description="Check a member's balance")
    async def show(
        self,
        ctx: ApplicationContext,
        member: Option(Member, "Whose balance (yours if omitted)", required=False, default=None),
    ):
        member = member or ctx.user
        amount = await self.db.get_balance(ctx.guild.id, member.id)
        embed = Embed(
            title=f"{COIN} Balance",
            # diff block for consistency with edits; negative balances show red
            description=f"{member.mention}\n```diff\n{amount}\n```",
            colour=Colour.gold(),
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @balance.command(name="top", description="The server's richest members")
    async def top(
        self,
        ctx: ApplicationContext,
        count: Option(int, "How many members to show", min_value=1, max_value=25, default=10),
    ):
        richest = await self.db.top(ctx.guild.id, count)
        in_debt = await self.db.bottom(ctx.guild.id, count)
        if not richest and not in_debt:
            await ctx.respond(":shrug:  **Nobody has any balance yet**", ephemeral=True)
            return

        def board(rows):
            return "\n".join(
                f"`{position}` <@{row['userID']}> — `{row['amount']}` {COIN}"
                for position, row in enumerate(rows, start=1)
            )

        embed = Embed(title=f"{COIN} Top balances", colour=Colour.gold())
        if richest:
            embed.add_field(name="💰 Richest", value=board(richest), inline=False)
        if in_debt:
            embed.add_field(name="📉 Most in debt", value=board(in_debt), inline=False)
        await ctx.respond(embed=embed, ephemeral=True)

    @balance.command(name="give", description="Give part of your balance to someone")
    async def give(
        self,
        ctx: ApplicationContext,
        member: Option(Member, "Who receives it"),
        amount: Option(int, "How much", min_value=1),
    ):
        if member.id == ctx.user.id:
            await ctx.respond(":interrobang:  **You already have it!**", ephemeral=True)
            return
        if member.bot:
            await ctx.respond(":interrobang:  **Bots have no use for money**", ephemeral=True)
            return
        ok = await self.db.transfer(ctx.guild.id, ctx.user.id, member.id, amount)
        if not ok:
            held = await self.db.get_balance(ctx.guild.id, ctx.user.id)
            await ctx.respond(
                f":no_entry:  **Not enough funds** — you have {held} {COIN}", ephemeral=True
            )
            return
        await ctx.respond(f"{COIN}  **{ctx.user.mention} gave {amount} to {member.mention}**")

    # -- Banker role -------------------------------------------------------------

    async def _edit_members(
        self,
        guild_id: int,
        members: list[Member],
        expression: str,
        actor_id: int,
        reason: str | None,
    ) -> Embed:
        """Apply an edit expression to each member; returns the public embed.

        Percentages are computed against each member's own balance, so `-30%`
        on several members scales each one individually.
        """
        results = []
        for member in members:
            before = await self.db.get_balance(guild_id, member.id)
            after = apply_amount(before, expression)
            if after != before:
                await self.db.adjust(guild_id, member.id, after - before, actor_id, reason)
            results.append((member, before, after))
        return change_embed(results, reason, expression)

    @balance.command(name="edit", description="Adjust balances: +500, -500, +30%, -30%")
    @is_banker()
    async def edit(
        self,
        ctx: ApplicationContext,
        amount: Option(str, "+500 adds, -500 removes, +30%/-30% scale"),
        member: Option(
            Member, "Whose balance (omit to pick several members)", required=False, default=None
        ),
        reason: Option(str, "Why (kept in the log)", required=False, default=None),
    ):
        if apply_amount(0, amount) is None:
            await ctx.respond(
                ":x:  **Invalid amount** — use `+500`, `-500`, `+30%` or `-30%`",
                ephemeral=True,
            )
            return
        if member is not None:
            if member.bot:
                await ctx.respond(":interrobang:  **Bots have no use for money**", ephemeral=True)
                return
            embed = await self._edit_members(ctx.guild.id, [member], amount, ctx.user.id, reason)
            await ctx.respond(embed=embed)
            return
        await ctx.respond(
            f"{COIN}  **Pick whose balances get `{amount}`**",
            view=BulkEditView(self, amount, reason),
            ephemeral=True,
        )

    @balance.command(name="set", description="Set a member's balance to an exact value")
    @is_banker()
    async def set_balance(
        self,
        ctx: ApplicationContext,
        member: Option(Member, "Whose balance"),
        amount: Option(int, "The new balance (may be negative)"),
        reason: Option(str, "Why (kept in the log)", required=False, default=None),
    ):
        if member.bot:
            await ctx.respond(":interrobang:  **Bots have no use for money**", ephemeral=True)
            return
        before = await self.db.get_balance(ctx.guild.id, member.id)
        if amount == before:
            await ctx.respond(
                f":shrug:  **{member.display_name}'s balance is already {amount}**", ephemeral=True
            )
            return
        await self.db.adjust(
            ctx.guild.id, member.id, amount - before, ctx.user.id, reason or "balance set"
        )
        await ctx.respond(embed=change_embed([(member, before, amount)], reason))

    @balance.command(name="log", description="Recent balance changes")
    @is_banker()
    async def log(
        self,
        ctx: ApplicationContext,
        member: Option(Member, "Filter by member", required=False, default=None),
        count: Option(int, "How many entries", min_value=1, max_value=25, default=10),
    ):
        rows = await self.db.get_log(ctx.guild.id, member.id if member else None, count)
        if not rows:
            await ctx.respond(":shrug:  **No transactions yet**", ephemeral=True)
            return
        lines = []
        for row in rows:
            # SQLite CURRENT_TIMESTAMP is UTC
            when = int(datetime.fromisoformat(row["txTime"]).replace(tzinfo=UTC).timestamp())
            line = f"<t:{when}:d> `{row['delta']:+d}` <@{row['userID']}> by <@{row['actorID']}>"
            if row["reason"]:
                line += f" — *{row['reason']}*"
            lines.append(line)
        embed = Embed(
            title=f"{COIN} Transaction log", description="\n".join(lines), colour=Colour.gold()
        )
        await ctx.respond(embed=embed, ephemeral=True)

    # -- Staff --------------------------------------------------------------------

    @balance.command(name="config", description="Choose which role manages balances (staff only)")
    @commands.has_guild_permissions(manage_guild=True)
    async def config(
        self,
        ctx: ApplicationContext,
        role: Option(Role, "Role allowed to add/remove currency", required=False, default=None),
        clear: Option(bool, "Reset: only staff manage balances", required=False, default=False),
    ):
        if clear:
            await self.db.set_banker_role(ctx.guild.id, None)
            await ctx.respond(
                ":gear:  **Cleared — only staff can manage balances now**", ephemeral=True
            )
            return
        if role is not None:
            await self.db.set_banker_role(ctx.guild.id, role.id)
            await ctx.respond(
                f":gear:  **Members with {role.mention} can now manage balances**", ephemeral=True
            )
            return
        current = await self.db.get_banker_role(ctx.guild.id)
        await ctx.respond(
            f":gear:  **Current banker role: <@&{current}>**"
            if current
            else ":gear:  **No banker role set — only staff can manage balances**",
            ephemeral=True,
        )

    async def cog_command_error(self, ctx: ApplicationContext, error: Exception):
        # Specific message for the banker gate; the rest goes to the global handler.
        if isinstance(error, NotBanker):
            message = (
                f":no_entry:  **You need the <@&{error.role_id}> role to manage balances**"
                if error.role_id
                else ":no_entry:  **Only staff can manage balances here** — an admin can"
                " allow a role with `/balance config`"
            )
            await ctx.respond(message, ephemeral=True)


def setup(bot: Bot):
    bot.add_cog(Balance(bot))
