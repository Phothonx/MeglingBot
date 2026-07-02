"""Persistence for the raid feature (db/raid.db).

Templates are per-user and portable across guilds. When a raid is launched the
template's info and roles are *snapshotted* into the raid, so editing or
deleting a template never breaks a live raid. Finished raids are archived to
RaidLog and removed from the live tables.

Tables:
    RaidTemplates(templateName, url, description, image, ownerID)
    TemplateRoles(templateName, roleName, roleIcon, maxSlots, ownerID)
    Raids(raidID, guildID, leaderID, templateName, title, description, url,
          image, raidTime, messageID, channelID)
    RaidRoles(raidID, roleName, roleIcon, maxSlots)
    Signups(signupID, userID, raidID, roleName, signupTime, signupRank)
    RaidLog(logID, guildID, leaderID, title, raidTime, roster)

Times are stored as naive local ISO strings (the bot host's timezone).
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# Signups with this role name mean "explicitly not coming".
ABSENT = "absent"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS RaidTemplates (
    templateName TEXT,
    url TEXT,
    description TEXT,
    image TEXT,
    ownerID INTEGER,
    PRIMARY KEY (templateName, ownerID)
);
CREATE TABLE IF NOT EXISTS TemplateRoles (
    templateName TEXT,
    roleName TEXT,
    roleIcon TEXT,
    maxSlots INTEGER,
    ownerID INTEGER,
    PRIMARY KEY (templateName, ownerID, roleName)
);
CREATE TABLE IF NOT EXISTS Raids (
    raidID INTEGER PRIMARY KEY AUTOINCREMENT,
    guildID INTEGER NOT NULL,
    leaderID INTEGER NOT NULL,
    templateName TEXT,
    title TEXT NOT NULL,
    description TEXT,
    url TEXT,
    image TEXT,
    raidTime TEXT NOT NULL,
    messageID INTEGER,
    channelID INTEGER,
    pingMessageID INTEGER
);
CREATE TABLE IF NOT EXISTS RaidRoles (
    raidID INTEGER,
    roleName TEXT,
    roleIcon TEXT,
    maxSlots INTEGER,
    PRIMARY KEY (raidID, roleName)
);
CREATE TABLE IF NOT EXISTS Signups (
    signupID INTEGER PRIMARY KEY AUTOINCREMENT,
    userID INTEGER NOT NULL,
    raidID INTEGER NOT NULL,
    roleName TEXT,
    signupTime TEXT DEFAULT CURRENT_TIMESTAMP,
    signupRank INTEGER,
    UNIQUE (userID, raidID)
);
CREATE TABLE IF NOT EXISTS RaidLog (
    logID INTEGER PRIMARY KEY AUTOINCREMENT,
    guildID INTEGER NOT NULL,
    leaderID INTEGER NOT NULL,
    title TEXT NOT NULL,
    raidTime TEXT NOT NULL,
    roster TEXT
);
"""


class RaidDB:
    def __init__(self, db_path: str = "db/raid.db"):
        self.db_path = db_path

    def _connect(self):
        return aiosqlite.connect(self.db_path)

    async def init(self) -> None:
        """Create the database and schema, migrating old live-raid tables if needed."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as db:
            # Pre-redesign Raids rows lack the snapshot columns and can't be
            # upgraded meaningfully; drop the (short-lived) live tables.
            cursor = await db.execute("PRAGMA table_info(Raids)")
            columns = [row[1] for row in await cursor.fetchall()]
            if columns and "guildID" not in columns:
                logger.warning("Old raid schema detected: dropping live raid tables")
                await db.execute("DROP TABLE Raids")
                await db.execute("DROP TABLE IF EXISTS Signups")
            await db.executescript(_SCHEMA)
            # Columns added after the redesign (CREATE IF NOT EXISTS won't add them).
            cursor = await db.execute("PRAGMA table_info(Raids)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "pingMessageID" not in columns:
                await db.execute("ALTER TABLE Raids ADD COLUMN pingMessageID INTEGER")
            await db.commit()
        logger.debug("raid.db schema ready")

    # -- Templates ---------------------------------------------------------------

    async def create_template(
        self,
        template_name: str,
        owner_id: int,
        description: str | None = None,
        url: str | None = None,
        image: str | None = None,
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                "INSERT OR REPLACE INTO RaidTemplates"
                " (templateName, url, description, image, ownerID) VALUES (?, ?, ?, ?, ?)",
                (template_name, url, description, image, owner_id),
            )
            await db.commit()
        logger.info("Template %r saved by user %s", template_name, owner_id)

    async def get_template(self, template_name: str, owner_id: int) -> aiosqlite.Row | None:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM RaidTemplates WHERE templateName = ? AND ownerID = ?",
                (template_name, owner_id),
            )
            return await cursor.fetchone()

    async def get_template_names(self, owner_id: int) -> list[str]:
        """All template names of a user (for slash command autocomplete)."""
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT templateName FROM RaidTemplates WHERE ownerID = ? ORDER BY templateName",
                (owner_id,),
            )
            return [row[0] for row in await cursor.fetchall()]

    async def remove_template(self, template_name: str, owner_id: int) -> bool:
        async with self._connect() as db:
            await db.execute(
                "DELETE FROM TemplateRoles WHERE templateName = ? AND ownerID = ?",
                (template_name, owner_id),
            )
            cursor = await db.execute(
                "DELETE FROM RaidTemplates WHERE templateName = ? AND ownerID = ?",
                (template_name, owner_id),
            )
            await db.commit()
        if cursor.rowcount == 0:
            return False
        logger.info("Template %r removed by user %s", template_name, owner_id)
        return True

    async def get_template_roles(self, template_name: str, owner_id: int) -> list[aiosqlite.Row]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT roleName, roleIcon, maxSlots FROM TemplateRoles"
                " WHERE templateName = ? AND ownerID = ?",
                (template_name, owner_id),
            )
            return list(await cursor.fetchall())

    async def add_template_role(
        self, template_name: str, owner_id: int, role_name: str, role_icon: str, max_slots: int
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                "INSERT OR REPLACE INTO TemplateRoles"
                " (templateName, roleName, roleIcon, maxSlots, ownerID) VALUES (?, ?, ?, ?, ?)",
                (template_name, role_name, role_icon, max_slots, owner_id),
            )
            await db.commit()
        logger.info("Role %r added to template %r by user %s", role_name, template_name, owner_id)

    async def remove_template_role(self, template_name: str, owner_id: int, role_name: str) -> bool:
        async with self._connect() as db:
            cursor = await db.execute(
                "DELETE FROM TemplateRoles WHERE templateName = ? AND roleName = ? AND ownerID = ?",
                (template_name, role_name, owner_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    # -- Live raids ----------------------------------------------------------------

    async def create_raid(
        self,
        guild_id: int,
        leader_id: int,
        title: str,
        raid_time: datetime,
        template: aiosqlite.Row,
        roles: list[aiosqlite.Row],
        message_id: int,
        channel_id: int,
    ) -> int:
        """Insert a raid with a full snapshot of its template. Returns the raid id."""
        async with self._connect() as db:
            cursor = await db.execute(
                "INSERT INTO Raids (guildID, leaderID, templateName, title, description,"
                " url, image, raidTime, messageID, channelID) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    guild_id,
                    leader_id,
                    template["templateName"],
                    title,
                    template["description"],
                    template["url"],
                    template["image"],
                    raid_time.isoformat(sep=" "),
                    message_id,
                    channel_id,
                ),
            )
            raid_id = cursor.lastrowid or 0  # lastrowid is always set after INSERT
            await db.executemany(
                "INSERT INTO RaidRoles (raidID, roleName, roleIcon, maxSlots) VALUES (?,?,?,?)",
                [(raid_id, r["roleName"], r["roleIcon"], r["maxSlots"]) for r in roles],
            )
            await db.commit()
        logger.info(
            "Raid %s (%r) launched by user %s in guild %s", raid_id, title, leader_id, guild_id
        )
        return raid_id

    async def get_raid(self, raid_id: int) -> aiosqlite.Row | None:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM Raids WHERE raidID = ?", (raid_id,))
            return await cursor.fetchone()

    async def get_raid_by_message(self, message_id: int) -> aiosqlite.Row | None:
        """Resolve a raid from its signup message (used by the persistent view)."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM Raids WHERE messageID = ?", (message_id,))
            return await cursor.fetchone()

    async def get_raid_by_ping_message(self, message_id: int) -> aiosqlite.Row | None:
        """Resolve a raid from its start-ping message (used by the Start button)."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM Raids WHERE pingMessageID = ?", (message_id,))
            return await cursor.fetchone()

    async def set_ping_message(self, raid_id: int, message_id: int | None) -> None:
        """Remember (or forget, with None) the start-ping message of a raid."""
        async with self._connect() as db:
            await db.execute(
                "UPDATE Raids SET pingMessageID = ? WHERE raidID = ?", (message_id, raid_id)
            )
            await db.commit()

    async def get_raid_roles(self, raid_id: int) -> list[aiosqlite.Row]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT roleName, roleIcon, maxSlots FROM RaidRoles WHERE raidID = ?", (raid_id,)
            )
            return list(await cursor.fetchall())

    async def update_raid(
        self, raid_id: int, *, title: str | None = None, raid_time: datetime | None = None
    ) -> None:
        async with self._connect() as db:
            if title is not None:
                await db.execute("UPDATE Raids SET title = ? WHERE raidID = ?", (title, raid_id))
            if raid_time is not None:
                await db.execute(
                    "UPDATE Raids SET raidTime = ? WHERE raidID = ?",
                    (raid_time.isoformat(sep=" "), raid_id),
                )
            await db.commit()
        logger.info("Raid %s updated (title=%r, time=%s)", raid_id, title, raid_time)

    # -- Signups ---------------------------------------------------------------------

    async def upsert_signup(self, raid_id: int, user_id: int, role_name: str) -> None:
        """Sign a user up, or switch their role if already signed up."""
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT 1 FROM Signups WHERE raidID = ? AND userID = ?", (raid_id, user_id)
            )
            if await cursor.fetchone():
                await db.execute(
                    "UPDATE Signups SET roleName = ? WHERE raidID = ? AND userID = ?",
                    (role_name, raid_id, user_id),
                )
                logger.info("User %s switched to %r in raid %s", user_id, role_name, raid_id)
            else:
                cursor = await db.execute(
                    "SELECT COALESCE(MAX(signupRank), 0) + 1 FROM Signups WHERE raidID = ?",
                    (raid_id,),
                )
                row = await cursor.fetchone()
                rank = row[0] if row else 1
                await db.execute(
                    "INSERT INTO Signups (userID, raidID, roleName, signupRank)"
                    " VALUES (?, ?, ?, ?)",
                    (user_id, raid_id, role_name, rank),
                )
                logger.info("User %s signed up as %r to raid %s", user_id, role_name, raid_id)
            await db.commit()

    async def remove_signup(self, raid_id: int, user_id: int) -> bool:
        async with self._connect() as db:
            cursor = await db.execute(
                "DELETE FROM Signups WHERE raidID = ? AND userID = ?", (raid_id, user_id)
            )
            await db.commit()
        if cursor.rowcount:
            logger.info("User %s withdrew from raid %s", user_id, raid_id)
        return cursor.rowcount > 0

    async def get_signups(self, raid_id: int) -> list[aiosqlite.Row]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT userID, roleName, signupRank FROM Signups"
                " WHERE raidID = ? ORDER BY signupRank",
                (raid_id,),
            )
            return list(await cursor.fetchall())

    async def count_role_signups(self, raid_id: int, role_name: str) -> int:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM Signups WHERE raidID = ? AND roleName = ?",
                (raid_id, role_name),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    # -- End of life: archive & history ---------------------------------------------

    async def due_raids(self) -> list[aiosqlite.Row]:
        """Raids whose start time has passed."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM Raids WHERE raidTime < ?", (datetime.now().isoformat(sep=" "),)
            )
            return list(await cursor.fetchall())

    async def archive_raid(self, raid_id: int) -> None:
        """Move a finished raid into RaidLog and drop it from the live tables."""
        raid = await self.get_raid(raid_id)
        if raid is None:
            return
        signups = await self.get_signups(raid_id)
        roster: dict[str, list[int]] = {}
        for signup in signups:
            roster.setdefault(signup["roleName"], []).append(signup["userID"])

        async with self._connect() as db:
            await db.execute(
                "INSERT INTO RaidLog (guildID, leaderID, title, raidTime, roster)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    raid["guildID"],
                    raid["leaderID"],
                    raid["title"],
                    raid["raidTime"],
                    json.dumps(roster),
                ),
            )
            await self._delete_raid(db, raid_id)
            await db.commit()
        logger.info("Raid %s (%r) archived", raid_id, raid["title"])

    async def delete_raid(self, raid_id: int) -> None:
        """Drop a raid without archiving it (cancellation)."""
        async with self._connect() as db:
            await self._delete_raid(db, raid_id)
            await db.commit()
        logger.info("Raid %s cancelled", raid_id)

    @staticmethod
    async def _delete_raid(db: aiosqlite.Connection, raid_id: int) -> None:
        await db.execute("DELETE FROM Signups WHERE raidID = ?", (raid_id,))
        await db.execute("DELETE FROM RaidRoles WHERE raidID = ?", (raid_id,))
        await db.execute("DELETE FROM Raids WHERE raidID = ?", (raid_id,))

    async def get_history(self, guild_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        """Most recent archived raids of a guild."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM RaidLog WHERE guildID = ? ORDER BY raidTime DESC LIMIT ?",
                (guild_id, limit),
            )
            return list(await cursor.fetchall())
