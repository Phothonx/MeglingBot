"""Persistence for the balance feature (db/balance.db).

Each member has one balance per guild; balances may go negative (debt). Every
change is recorded in Transactions for accountability. The banker role
(who may add/remove currency) is configured per guild, like the raid leader.

Tables:
    Balances(guildID, userID, amount)
    Transactions(txID, guildID, userID, delta, actorID, reason, txTime)
    GuildSettings(guildID, bankerRoleID)
"""

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS Balances (
    guildID INTEGER NOT NULL,
    userID INTEGER NOT NULL,
    amount INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guildID, userID)
);
CREATE TABLE IF NOT EXISTS Transactions (
    txID INTEGER PRIMARY KEY AUTOINCREMENT,
    guildID INTEGER NOT NULL,
    userID INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    actorID INTEGER NOT NULL,
    reason TEXT,
    txTime TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS GuildSettings (
    guildID INTEGER PRIMARY KEY,
    bankerRoleID INTEGER
);
"""


class BalanceDB:
    def __init__(self, db_path: str = "db/balance.db"):
        self.db_path = db_path

    def _connect(self):
        return aiosqlite.connect(self.db_path)

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        logger.debug("balance.db schema ready")

    # -- Per-guild settings ----------------------------------------------------

    async def set_banker_role(self, guild_id: int, role_id: int | None) -> None:
        """Set (or clear, with None) the role allowed to add/remove currency."""
        async with self._connect() as db:
            await db.execute(
                "INSERT OR REPLACE INTO GuildSettings (guildID, bankerRoleID) VALUES (?, ?)",
                (guild_id, role_id),
            )
            await db.commit()
        logger.info("Banker role of guild %s set to %s", guild_id, role_id)

    async def get_banker_role(self, guild_id: int) -> int | None:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT bankerRoleID FROM GuildSettings WHERE guildID = ?", (guild_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    # -- Balances -----------------------------------------------------------------

    async def get_balance(self, guild_id: int, user_id: int) -> int:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT amount FROM Balances WHERE guildID = ? AND userID = ?",
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def adjust(
        self, guild_id: int, user_id: int, delta: int, actor_id: int, reason: str | None = None
    ) -> int:
        """Add `delta` (may be negative) to a member's balance and log it.

        Balances may go negative (debt). Returns the new balance.
        """
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT amount FROM Balances WHERE guildID = ? AND userID = ?",
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            new_amount = (row[0] if row else 0) + delta
            await db.execute(
                "INSERT OR REPLACE INTO Balances (guildID, userID, amount) VALUES (?, ?, ?)",
                (guild_id, user_id, new_amount),
            )
            await db.execute(
                "INSERT INTO Transactions (guildID, userID, delta, actorID, reason)"
                " VALUES (?, ?, ?, ?, ?)",
                (guild_id, user_id, delta, actor_id, reason),
            )
            await db.commit()
        logger.info(
            "Balance of user %s in guild %s changed by %+d (by %s): now %d",
            user_id,
            guild_id,
            delta,
            actor_id,
            new_amount,
        )
        return new_amount

    async def transfer(self, guild_id: int, sender_id: int, recipient_id: int, amount: int) -> bool:
        """Move `amount` between two members atomically.

        Returns False when the sender's funds are insufficient.
        """
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT amount FROM Balances WHERE guildID = ? AND userID = ?",
                (guild_id, sender_id),
            )
            row = await cursor.fetchone()
            if (row[0] if row else 0) < amount:
                return False
            await db.execute(
                "UPDATE Balances SET amount = amount - ? WHERE guildID = ? AND userID = ?",
                (amount, guild_id, sender_id),
            )
            await db.execute(
                "INSERT INTO Balances (guildID, userID, amount) VALUES (?, ?, ?)"
                " ON CONFLICT (guildID, userID) DO UPDATE SET amount = amount + ?",
                (guild_id, recipient_id, amount, amount),
            )
            await db.executemany(
                "INSERT INTO Transactions (guildID, userID, delta, actorID, reason)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (guild_id, sender_id, -amount, sender_id, f"transfer to {recipient_id}"),
                    (guild_id, recipient_id, amount, sender_id, f"transfer from {sender_id}"),
                ],
            )
            await db.commit()
        logger.info(
            "Transfer of %d from %s to %s in guild %s", amount, sender_id, recipient_id, guild_id
        )
        return True

    async def top(self, guild_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        """Highest balances of a guild."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT userID, amount FROM Balances WHERE guildID = ? AND amount > 0"
                " ORDER BY amount DESC LIMIT ?",
                (guild_id, limit),
            )
            return list(await cursor.fetchall())

    async def bottom(self, guild_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        """Deepest debts of a guild (negative balances, most indebted first)."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT userID, amount FROM Balances WHERE guildID = ? AND amount < 0"
                " ORDER BY amount ASC LIMIT ?",
                (guild_id, limit),
            )
            return list(await cursor.fetchall())

    async def get_log(
        self, guild_id: int, user_id: int | None = None, limit: int = 10
    ) -> list[aiosqlite.Row]:
        """Latest transactions of a guild, optionally for a single member."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            if user_id is None:
                cursor = await db.execute(
                    "SELECT * FROM Transactions WHERE guildID = ? ORDER BY txID DESC LIMIT ?",
                    (guild_id, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM Transactions WHERE guildID = ? AND userID = ?"
                    " ORDER BY txID DESC LIMIT ?",
                    (guild_id, user_id, limit),
                )
            return list(await cursor.fetchall())
