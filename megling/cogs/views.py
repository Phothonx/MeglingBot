import importlib
import logging

from discord import ApplicationContext, Bot, SlashCommandGroup
from discord.ext import commands

logger = logging.getLogger(__name__)


class Views(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

        # https://embed.dan.onl/

    views = SlashCommandGroup("views", description="Make views and embeds")

    @views.command(name="setup")
    async def setup(
        self,
        ctx: ApplicationContext,
        embed_template: str = "",
        view_template: str = "",
        message: str = "",
    ):
        if embed_template != "":
            try:
                embed_mod = importlib.import_module(
                    f"..templates.embeds.{embed_template}", package=__package__
                )
                embed = getattr(embed_mod, "embed", None)
            except Exception:
                logger.exception("Failed to load embed template: %s", embed_template)
                await ctx.respond(":x: **Failed to load embed template**", ephemeral=True)
                return
        else:
            embed = None

        if view_template != "":
            try:
                view_mod = importlib.import_module(
                    f"..templates.views.{view_template}", package=__package__
                )
                view = getattr(view_mod, "view", None)
            except Exception:
                logger.exception("Failed to load view template: %s", view_template)
                await ctx.respond(":x: **Failed to load view template**", ephemeral=True)
                return
        else:
            view = None

        await ctx.channel.send(content=message, embed=embed, view=view)


def setup(bot: Bot):
    bot.add_cog(Views(bot))
