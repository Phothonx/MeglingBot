"""Administration and utility commands.

    /ping             everyone: latency check
    /admin prune      staff (Manage Messages): bulk-delete recent messages
    /admin reload     bot owner: hot-reload extensions after a code change

The /admin group is only shown to administrators (default_member_permissions);
each command additionally enforces its own runtime check.
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

from megling import extloader


class Admin(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @slash_command(name="ping", description="Check the bot's latency")
    async def ping(self, ctx: ApplicationContext):
        await ctx.respond(f"**:inbox_tray:  Pong! {round(self.bot.latency * 1000)} ms**")

    admin = SlashCommandGroup(
        "admin",
        description="Bot administration",
        default_member_permissions=Permissions(administrator=True),
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

    @admin.command(name="reload", description="Reload bot extensions (owner only)")
    @commands.is_owner()
    async def reload(
        self,
        ctx: ApplicationContext,
        extension: Option(
            str,
            "Extension to reload (all of them if omitted)",
            choices=extloader.extensions,
            default=None,
        ),
    ):
        await ctx.defer(ephemeral=True)
        extloader.load_extensions(self.bot, extension)
        await self.bot.sync_commands()
        await ctx.followup.send(
            f":arrows_clockwise:  **Reloaded `{extension}`**"
            if extension
            else ":arrows_clockwise:  **Reloaded all extensions**"
        )


def setup(bot: Bot):
    bot.add_cog(Admin(bot))
