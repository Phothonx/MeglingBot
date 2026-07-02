"""Bot owner commands — manage the bot process itself, not a server.

    /owner reload     hot-reload extensions after a code change
    /owner guilds     list the servers the bot is in
    /owner shutdown   log out and stop the process

Every command is gated by is_owner(). If OWNER_GUILD_ID is set in .env, the
whole group is registered only in that guild: it stays invisible on every
other server and updates instantly (guild commands skip global propagation).
Without it, the group is global and only the runtime check protects it.
"""

import logging
from os import getenv

from discord import (
    ApplicationContext,
    Bot,
    Colour,
    Embed,
    InteractionContextType,
    Option,
    Permissions,
    SlashCommandGroup,
)
from discord.ext import commands

from megling import extloader

logger = logging.getLogger(__name__)

_owner_guild = getenv("OWNER_GUILD_ID")


class Owner(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    owner = SlashCommandGroup(
        "owner",
        description="Bot owner commands",
        guild_ids=[int(_owner_guild)] if _owner_guild else None,
        default_member_permissions=Permissions(administrator=True),
        contexts={InteractionContextType.guild},
    )

    async def cog_check(self, ctx: ApplicationContext) -> bool:
        return await self.bot.is_owner(ctx.author)

    @owner.command(name="reload", description="Reload bot extensions")
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

    @owner.command(name="guilds", description="List the servers the bot is in")
    async def guilds(self, ctx: ApplicationContext):
        lines = [
            f"**{guild.name}** — {guild.member_count} members (id `{guild.id}`)"
            for guild in self.bot.guilds
        ]
        embed = Embed(
            title=f"{len(lines)} server(s)", description="\n".join(lines), colour=Colour.blurple()
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @owner.command(name="shutdown", description="Log out and stop the bot")
    async def shutdown(self, ctx: ApplicationContext):
        logger.warning("Shutdown requested by %s", ctx.user)
        await ctx.respond(":electric_plug:  **Shutting down…**", ephemeral=True)
        await self.bot.close()


def setup(bot: Bot):
    bot.add_cog(Owner(bot))
