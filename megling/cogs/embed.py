"""Embed poster: publish designed embeds without touching the bot's code.

    /embed create   quick embeds through a modal (title, text, colour, image)
    /embed json     full-fidelity embeds from JSON — design on https://embed.dan.onl
                    or https://discohook.org, then paste the JSON or attach a file

Requires Manage Messages; the bot posts in the channel the command is used in.
"""

import json
import logging

import discord
from discord import (
    ApplicationContext,
    Attachment,
    Bot,
    Colour,
    Embed,
    InputTextStyle,
    Interaction,
    InteractionContextType,
    Option,
    Permissions,
    SlashCommandGroup,
    ui,
)
from discord.ext import commands

from megling.utils import valid_url

logger = logging.getLogger(__name__)


def parse_colour(text: str) -> Colour | None:
    """Parse '#5865F2' / '5865F2' hex colours."""
    text = text.strip().lstrip("#")
    try:
        return Colour(int(text, 16))
    except ValueError:
        return None


def extract_embeds(data: dict | list) -> list[Embed]:
    """Accept a single embed object, a list, or a discohook-style {"embeds": [...]}."""
    if isinstance(data, dict) and "embeds" in data:
        data = data["embeds"]
    if isinstance(data, dict):
        data = [data]
    return [Embed.from_dict(item) for item in data[:10]]  # Discord caps at 10 embeds


class EmbedModal(ui.Modal):
    def __init__(self):
        super().__init__(title="Create an embed")
        self.title_input = ui.InputText(label="Title", required=False, max_length=256)
        self.body_input = ui.InputText(
            label="Text (markdown works)", style=InputTextStyle.long, max_length=4000
        )
        self.colour_input = ui.InputText(
            label="Colour (hex, optional)", placeholder="#5865F2", required=False, max_length=7
        )
        self.image_input = ui.InputText(
            label="Image link (optional)", required=False, max_length=500
        )
        self.footer_input = ui.InputText(label="Footer (optional)", required=False, max_length=2048)
        for item in (
            self.title_input,
            self.body_input,
            self.colour_input,
            self.image_input,
            self.footer_input,
        ):
            self.add_item(item)

    async def callback(self, interaction: Interaction):
        colour = Colour.blurple()
        if self.colour_input.value:
            colour = parse_colour(self.colour_input.value)
            if colour is None:
                await interaction.response.send_message(
                    ":x:  **Invalid colour** — use hex like `#5865F2`", ephemeral=True
                )
                return

        image = (self.image_input.value or "").strip()
        if image and not valid_url(image):
            await interaction.response.send_message(
                ":x:  **The image link is not a valid URL** — it must start with"
                " `http://` or `https://`",
                ephemeral=True,
            )
            return

        embed = Embed(
            title=self.title_input.value or None,
            description=self.body_input.value,
            colour=colour,
        )
        if image:
            embed.set_image(url=image)
        if self.footer_input.value:
            embed.set_footer(text=self.footer_input.value)

        try:
            # The posted embed is the modal response itself: no confirmation needed.
            await interaction.response.send_message(embed=embed)
        except discord.HTTPException as error:
            await interaction.followup.send(
                f":x:  **Discord rejected the embed:** {error.text}", ephemeral=True
            )


class EmbedCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    embed = SlashCommandGroup(
        "embed",
        description="Post embeds",
        default_member_permissions=Permissions(manage_messages=True),
        contexts={InteractionContextType.guild},
    )

    @embed.command(name="create", description="Create a simple embed with a form")
    async def create(self, ctx: ApplicationContext):
        await ctx.send_modal(EmbedModal())

    @embed.command(name="json", description="Post embed(s) from JSON (embed.dan.onl, discohook)")
    async def from_json(
        self,
        ctx: ApplicationContext,
        text: Option(str, "The JSON, pasted", required=False, default=None),
        file: Option(Attachment, "Or a .json file", required=False, default=None),
    ):
        if not text and not file:
            await ctx.respond(":x:  **Give me JSON text or a .json file**", ephemeral=True)
            return
        raw = text
        if file:
            if file.size > 100_000:
                await ctx.respond(":x:  **File too large**", ephemeral=True)
                return
            raw = (await file.read()).decode("utf-8", errors="replace")

        try:
            embeds = extract_embeds(json.loads(raw))
            if not embeds:
                raise ValueError("no embeds found")
            # The posted embeds are the command response itself.
            await ctx.respond(embeds=embeds)
        except (ValueError, KeyError, TypeError) as error:
            await ctx.respond(f":x:  **Invalid embed JSON:** {error}", ephemeral=True)
        except discord.HTTPException as error:
            await ctx.respond(f":x:  **Discord rejected the embed:** {error.text}", ephemeral=True)


def setup(bot: Bot):
    bot.add_cog(EmbedCog(bot))
