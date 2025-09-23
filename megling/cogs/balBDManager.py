import aiosqlite
from megling.logsetup import setupLogger

logger = setupLogger(__name__)

# bal.db:
# Bals(balID, balName, description, ownerID, amount)
# Perms(balID, userID, add, take, admin)
# Logs(balID, userID, amount, reason)

class balDB:
  def __init__(self, db_path: str = "db/bal.db"):
    self.db_path = db_path

  async def checkup(self):
    async with aiosqlite.connect(self.db_path) as db:
      logger.info("[~~] SQLite bal.db checkup...")
      await db.execute("""
CREATE TABLE IF NOT EXISTS Bals (
  balID INTEGER PRIMARY KEY AUTOINCREMENT,
  balName TEXT,
  description TEXT,
  ownerID INTEGER,
  amount INTEGER
);
      """)
      await db.execute("""
CREATE TABLE IF NOT EXISTS Perms (
  balID INTEGER,
  userID INTEGER,
  add BOOLEAN,
  take BOOLEAN,
  admin BOOLEAN,
  PRIMARY KEY (balID, userID)
);
      """)
      await db.execute("""
CREATE TABLE IF NOT EXISTS Logs (
  balID INTEGER PRIMARY KEY,
  userID INTEGER,
  amount INTEGER,
  reason TEXT
);
      """)
    await db.commit()
    logger.info("[OK] SQLite bal.db checkup completed")


  async def create_bal(
    self,
    bal_name: str,
    description: str,
    owner_id: int,
    amount: int,
  ):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO Bals (balName, description, ownerID, amount) VALUES (?, ?, ?, ?)",
        (bal_name, description, owner_id, amount)
      )
      await db.commit()
      logger.info(f"[DB] Created bal: {bal_name} owned by {owner_id}")


  async def get_bal(
    self,
    bal_id: int
  ):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT * FROM Bals WHERE balID = ?",
        (raid_id,)
      )
      bal = await cursor.fetchone()
      if not bal:
        return None
      bal_name, description, owner_id, amount = bal
      return (bal_name, description, owner_id, amount)


  async def remove_bal(
    self,
    bal_id: int
  ) -> bool:
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "DELETE FROM Bals WHERE balID = ?",
        (bal_id,)
      )
      await db.commit()
      if cursor.rowcount == 0:
        logger.warning(f"[DB] Bal not found to be removed: {bal_id}")
        return False
      else:
        logger.info(f"[DB] RBal removed: {bal_id}")
        return True


  async def create_perm(
    self,
    bal_id: str,
    user_id: int,
    add: bool,
    take: bool,
    admin: bool,
  ):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO Perms (balID, userID, add, take, admin) VALUES (?, ?, ?, ?, ?)",
        (bal_id, user_id, add, take, admin)
      )
      await db.commit()
      logger.info(f"[DB] Created perm for {user_id} to bal {bal_id}")


  async def get_perm(
    self,
    bal_id: int,
    user_id: int
  ):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT * FROM Perms WHERE balID = ? AND userID = ?",
        (bal_id, user_id)
      )
      perm = await cursor.fetchone()
      if not perm:
        return None
      bal_id, user_id, add, take, admin = bal
      return (bal_id, user_id, add, take, admin)

  async def remove_perm(
    self,
    bal_id: int,
    user_id: int
  ) -> bool:
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "DELETE FROM Perms WHERE WHERE balID = ? AND userID = ?",
        (bal_id, user_id)
      )
      await db.commit()
      if cursor.rowcount == 0:
        logger.warning(f"[DB] Perm not found to be removed: user {user_id}, bal {bal_id}")
        return False
      else:
        logger.info(f"[DB] Perm removed: user {user_id}, bal {bal_id}")
        return True


  async def create_log(
    self,
    bal_id: str,
    user_id: int,
    amount: int,
    reason: str
  ):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO Logs (balID, userID, amount, reason) VALUES (?, ?, ?, ?)",
        (bal_id, user_id, amount, reason)
      )
      await db.commit()
      logger.info(f"[DB] Created log: {bal_id} owned by {user_id}")


  async def get_logs(
    self,
    bal_id: int,
  ): async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT * FROM Logs WHERE balID = ?",
        (bal_id, )
      )
      return await cursor.fetchall()
