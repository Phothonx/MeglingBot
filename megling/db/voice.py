"""Persistence for the voice creator feature (db/voice.db).

Table names predate this module and are kept for compatibility with
existing databases:
    GuildChannels(guildID PK, channelID)          -- the lobby channel of each guild
    VoiceChannels(channelID PK, guildID, ownerID) -- currently active temp channels
"""

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


class VoiceDB:
    def __init__(self, db_path: str = "db/voice.db"):
        self.db_path = db_path

    async def init(self) -> None:
        """Create the database file and schema if they don't exist yet."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS GuildChannels ("
                "guildID INTEGER PRIMARY KEY, channelID INTEGER)"
            )
            await db.execute(
                "CREATE TABLE IF NOT EXISTS VoiceChannels ("
                "channelID INTEGER PRIMARY KEY, guildID INTEGER, ownerID INTEGER)"
            )
            await db.commit()
        logger.debug("voice.db schema ready")

    # -- Lobby (the join-to-create channel, one per guild) --------------------

    async def get_lobby(self, guild_id: int) -> int | None:
        """Return the lobby channel id of a guild, or None if not set up."""
        async with (
            aiosqlite.connect(self.db_path) as db,
            db.execute(
                "SELECT channelID FROM GuildChannels WHERE guildID = ?", (guild_id,)
            ) as cursor,
        ):
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_lobby(self, guild_id: int, channel_id: int) -> None:
        """Register (or replace) the lobby channel of a guild."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO GuildChannels (guildID, channelID) VALUES (?, ?)",
                (guild_id, channel_id),
            )
            await db.commit()
        logger.info("Lobby of guild %s set to channel %s", guild_id, channel_id)

    # -- Temporary channels ----------------------------------------------------

    async def add_temp_channel(self, channel_id: int, guild_id: int, owner_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO VoiceChannels (channelID, guildID, ownerID)"
                " VALUES (?, ?, ?)",
                (channel_id, guild_id, owner_id),
            )
            await db.commit()
        logger.info("Temp channel %s created for user %s", channel_id, owner_id)

    async def remove_temp_channel(self, channel_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM VoiceChannels WHERE channelID = ?", (channel_id,))
            await db.commit()

    async def get_owner(self, channel_id: int) -> int | None:
        """Return the owner of a temp channel, or None if the channel is not tracked."""
        async with (
            aiosqlite.connect(self.db_path) as db,
            db.execute(
                "SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (channel_id,)
            ) as cursor,
        ):
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_owner(self, channel_id: int, owner_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE VoiceChannels SET ownerID = ? WHERE channelID = ?",
                (owner_id, channel_id),
            )
            await db.commit()
        logger.info("Temp channel %s claimed by user %s", channel_id, owner_id)

    async def all_temp_channels(self) -> list[int]:
        """Return the ids of every tracked temp channel (used by cleanup)."""
        async with (
            aiosqlite.connect(self.db_path) as db,
            db.execute("SELECT channelID FROM VoiceChannels") as cursor,
        ):
            return [row[0] for row in await cursor.fetchall()]
