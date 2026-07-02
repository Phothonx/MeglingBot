"""Server staff commands — usable by admins/moderators of any guild.

    /ping           everyone: latency check
    /admin prune    staff (Manage Messages): bulk-delete recent messages

Authority comes from Discord guild permissions, so every server that invites
the bot manages access itself (Server Settings > Integrations). Commands that
belong to the bot's owner live in the owner cog instead.
"""

from discord import (
    ApplicationContext,
    Bot,
    InteractionContextType,
    Option,
    Permissions,
    SlashCommandGroup,
    slash_command,
)
from discord.ext import commands


class Admin(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(name="ping", description="Check the bot's latency")
    async def ping(self, ctx: ApplicationContext):
        await ctx.respond(f"**:inbox_tray:  Pong! {round(self.bot.latency * 1000)} ms**")

    admin = SlashCommandGroup(
        "admin",
        description="Server administration",
        default_member_permissions=Permissions(manage_messages=True),
        contexts={InteractionContextType.guild},
    )

    @admin.command(name="prune", description="Delete the last messages of this channel")
    @commands.has_guild_permissions(manage_messages=True)
    async def prune(
        self,
        ctx: ApplicationContext,
        number: Option(int, "How many messages to delete", min_value=1, max_value=100, default=5),
    ):
        await ctx.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=number)
        await ctx.followup.send(
            f":wastebasket:  **Deleted {len(deleted)} message(s)**", ephemeral=True
        )


def setup(bot: Bot):
    bot.add_cog(Admin(bot))
