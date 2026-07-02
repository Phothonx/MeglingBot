"""Voice creator: join the lobby channel, get your own temporary voice channel.

The member who triggers the creation owns the channel and receives Discord's
native `Manage Channel` / `Manage Permissions` on it, so renaming, locking,
hiding or limiting the channel is done through Discord's own UI — no bot
commands needed. The bot only handles creation, deletion and ownership:

    /vc setup [name]  (Manage Server) create or replace the guild's lobby
    /vc claim         take ownership of your current channel if the owner left
    /vc clean         (Manage Server) delete stale temp channels immediately

Empty temp channels are deleted as soon as their last member leaves; a daily
task catches anything missed while the bot was offline.
"""

import logging

import discord
from discord import (
    ApplicationContext,
    Bot,
    InteractionContextType,
    Member,
    PermissionOverwrite,
    SlashCommandGroup,
    VoiceChannel,
    VoiceState,
)
from discord.ext import commands, tasks

from megling.db.voice import VoiceDB

logger = logging.getLogger(__name__)

# What the owner can do on their own channel: everything channel-local
# (rename, user limit, lock/hide via permissions, kick by moving members).
OWNER_OVERWRITE = PermissionOverwrite(
    view_channel=True,  # owner keeps access even after hiding/locking @everyone
    connect=True,
    manage_channels=True,
    manage_permissions=True,
    move_members=True,
)


class Voice(commands.Cog):
    """Temporary voice channels created on demand ("join to create")."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.db = VoiceDB()
        self.daily_cleanup.start()

    def cog_unload(self):
        self.daily_cleanup.cancel()

    # -- Channel lifecycle -----------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        if before.channel == after.channel:
            return  # mute/deafen/stream change, not a move

        if after.channel is not None:
            lobby_id = await self.db.get_lobby(member.guild.id)
            if after.channel.id == lobby_id:
                await self._spawn_temp_channel(member, after.channel)

        if before.channel is not None:
            await self._delete_if_empty(before.channel)

    async def _spawn_temp_channel(self, member: Member, lobby: VoiceChannel):
        """Create a temp channel owned by `member` and move them into it."""
        try:
            channel = await member.guild.create_voice_channel(
                name=f"{member.display_name}'s channel",
                category=lobby.category,
                overwrites={member: OWNER_OVERWRITE},
                reason=f"Voice creator: channel for {member.display_name}",
            )
        except discord.HTTPException:
            logger.exception("Failed to create temp channel for user %s", member.id)
            return

        await self.db.add_temp_channel(channel.id, member.guild.id, member.id)
        try:
            await member.move_to(channel)
        except discord.HTTPException:
            # Member already left the lobby: drop the channel we just created.
            logger.warning("Could not move user %s to their temp channel", member.id)
            await self._delete_if_empty(channel)

    async def _delete_if_empty(self, channel: VoiceChannel):
        """Delete a temp channel once nobody is left in it."""
        if channel.members or await self.db.get_owner(channel.id) is None:
            return
        try:
            await channel.delete(reason="Voice creator: channel is empty")
        except discord.NotFound:
            pass  # already gone, just forget it
        except discord.HTTPException:
            logger.exception("Failed to delete temp channel %s", channel.id)
        await self.db.remove_temp_channel(channel.id)

    # -- Stale channel cleanup (bot restarts, missed events) --------------------

    @tasks.loop(hours=24)
    async def daily_cleanup(self):
        await self.cleanup_stale_channels()

    @daily_cleanup.before_loop
    async def prepare(self):
        await self.db.init()
        await self.bot.wait_until_ready()

    async def cleanup_stale_channels(self) -> int:
        """Drop tracked channels that no longer exist or sit empty. Returns count."""
        removed = 0
        for channel_id in await self.db.all_temp_channels():
            channel = self.bot.get_channel(channel_id)
            if channel is not None and channel.members:
                continue  # still in use
            if channel is not None:
                try:
                    await channel.delete(reason="Voice creator: stale channel")
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    logger.exception("Failed to delete stale channel %s", channel_id)
                    continue  # retry on next pass
            await self.db.remove_temp_channel(channel_id)
            removed += 1
        if removed:
            logger.info("Cleaned %d stale temp channel(s)", removed)
        return removed

    # -- Commands ----------------------------------------------------------------

    vc = SlashCommandGroup(
        "vc",
        description="Voice creator",
        contexts={InteractionContextType.guild},
    )

    @vc.command(name="setup", description="Create (or replace) the voice creator lobby")
    @commands.has_guild_permissions(manage_guild=True)
    async def setup(self, ctx: ApplicationContext, name: str = "➕ Create a channel"):
        lobby = await ctx.guild.create_voice_channel(name, reason="Voice creator lobby")

        # A guild has a single lobby: drop the previous one if it still exists.
        old_lobby_id = await self.db.get_lobby(ctx.guild.id)
        if old_lobby_id:
            old_lobby = ctx.guild.get_channel(old_lobby_id)
            if isinstance(old_lobby, VoiceChannel):
                await old_lobby.delete(reason="Voice creator: lobby replaced")

        await self.db.set_lobby(ctx.guild.id, lobby.id)
        await ctx.respond(
            f":gear:  **Lobby {lobby.mention} created — join it to get your own channel!**",
            ephemeral=True,
        )

    @vc.command(name="claim", description="Take ownership of your channel if the owner left")
    async def claim(self, ctx: ApplicationContext):
        channel = ctx.user.voice.channel if ctx.user.voice else None
        if channel is None:
            await ctx.respond(
                ":interrobang:  **You are not connected to a voice channel**", ephemeral=True
            )
            return

        owner_id = await self.db.get_owner(channel.id)
        if owner_id is None:
            await ctx.respond(
                ":interrobang:  **This channel is not managed by the voice creator**",
                ephemeral=True,
            )
            return
        if owner_id == ctx.user.id:
            await ctx.respond(":crown:  **You already own this channel**", ephemeral=True)
            return
        if any(member.id == owner_id for member in channel.members):
            await ctx.respond(":interrobang:  **The owner is still here**", ephemeral=True)
            return

        # Transfer both the database record and the Discord permissions.
        await self.db.set_owner(channel.id, ctx.user.id)
        old_owner = ctx.guild.get_member(owner_id)
        if old_owner:
            await channel.set_permissions(old_owner, overwrite=None)
        await channel.set_permissions(ctx.user, overwrite=OWNER_OVERWRITE)
        await ctx.respond(":crown:  **You now own this channel**")

    @vc.command(name="clean", description="Delete stale temporary channels now")
    @commands.has_guild_permissions(manage_guild=True)
    async def clean(self, ctx: ApplicationContext):
        await ctx.defer(ephemeral=True)
        removed = await self.cleanup_stale_channels()
        await ctx.followup.send(
            f":wastebasket:  **Removed {removed} stale channel(s)**", ephemeral=True
        )


def setup(bot: Bot):
    bot.add_cog(Voice(bot))
