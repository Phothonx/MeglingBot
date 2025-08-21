import aiosqlite
from datetime import datetime
from megling.logsetup import setupLogger
from typing import List, Tuple

logger = setupLogger(__name__)

# raid.db
# RaidTemplates(templateName, url, description, image, ownerID)
# TemplateRoles(templateName, roleName, roleIcon, maxSlots, ownerID)
# Raids(raidID, leaderID, templateName, title, raidTime, messageID, channelID)
# Signups(signupID, userID, raidID, roleName, signupTime, signupRank)

class RaidDB:
  def __init__(self, db_path: str = "db/raid.db"):
    self.db_path = db_path

  async def checkup(self):
    async with aiosqlite.connect(self.db_path) as db:
      logger.info("[~~] SQLite raid.db checkup...")
      await db.execute("""
CREATE TABLE IF NOT EXISTS RaidTemplates (
  templateName TEXT,
  url TEXT,
  description TEXT,
  image TEXT,
  ownerID INTEGER,
  PRIMARY KEY (templateName, ownerID)
);
      """)
      await db.execute("""
CREATE TABLE IF NOT EXISTS TemplateRoles (
  templateName TEXT,
  roleName TEXT,
  roleIcon TEXT,
  maxSlots INTEGER,
  ownerID INTEGER,
  PRIMARY KEY (templateName, ownerID, roleName)
);
      """)
      await db.execute("""
CREATE TABLE IF NOT EXISTS Raids (
  raidID INTEGER PRIMARY KEY AUTOINCREMENT,
  leaderID INTEGER NOT NULL,
  templateName TEXT NOT NULL,
  title TEXT NOT NULL,
  raidTime DATETIME NOT NULL,
  messageID INTEGER,
  channelID INTEGER
);
      """)
      await db.execute("""
CREATE TABLE IF NOT EXISTS Signups (
  signupID INTEGER PRIMARY KEY AUTOINCREMENT,
  userID INTEGER NOT NULL,
  raidID INTEGER NOT NULL,
  roleName TEXT,
  signupTime DATETIME DEFAULT CURRENT_TIMESTAMP,
  signupRank INTEGER,
  UNIQUE(userID, raidID)
);
      """)
      await db.commit()
      logger.info("[OK] SQLite raid.db checkup completed")

  async def get_raid(self, raid_id: int):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT * FROM Raids WHERE raidID = ?",
        (raid_id,)
      )
      raid = await cursor.fetchone()
      if not raid:
        return None
      raid_id, leader_id, template_name, title, raid_time_str, message_id, channel_id = raid
      raid_time = datetime.fromisoformat(raid_time_str)
      return (raid_id, leader_id, template_name, title, raid_time, message_id, channel_id)

  async def get_template(self, template_name: str, owner_id: int):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT * FROM RaidTemplates WHERE templateName = ? AND ownerID = ?",
        (template_name, owner_id)
      )
      return await cursor.fetchone()

  async def get_template_roles(self, template_name: str, owner_id: int):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT roleName, roleIcon, maxSlots FROM TemplateRoles WHERE templateName = ? AND ownerID = ?",
        (template_name, owner_id)
      )
      return await cursor.fetchall()

  async def create_template(
    self,
    template_name: str,
    url: str | None,
    description: str | None,
    image: str | None,
    owner_id: int | None
  ):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO RaidTemplates (templateName, url, description, image, ownerID) VALUES (?, ?, ?, ?, ?)",
        (template_name, url, description, image, owner_id)
      )
      await db.commit()
      logger.info(f"[DB] Created template: {template_name} by {owner_id}")

  async def remove_template(
    self,
    template_name:str,
    owner_id: int
  ):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "DELETE FROM TemplateRoles WHERE templateName = ? AND ownerID = ?",
        (template_name, owner_id)
      )
      cursor = await db.execute(
        "DELETE FROM RaidTemplates WHERE templateName = ? AND ownerID = ?",
        (template_name, owner_id)
      )
      await db.commit()
      if cursor.rowcount == 0:
        return False
      else:
        logger.info(f"[DB] Removed template from template: {template_name} by {owner_id}")
        return True


  async def add_template_role(
    self,
    template_name:str,
    role_name:str,
    role_icon:str,
    max_slots:int,
    owner_id: int,
  ):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT OR REPLACE INTO TemplateRoles (templateName, roleName, roleIcon, maxSlots, ownerID) VALUES (?, ?, ?, ?, ?)",
        (template_name, role_name, role_icon, max_slots, owner_id)
      )
      await db.commit()
      logger.info(f"[DB] Added role to template: {role_name} to {template_name} by {owner_id}")


  async def remove_template_role(
    self,
    template_name:str,
    role_name:str,
    owner_id: int
  )-> bool:
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "DELETE FROM TemplateRoles WHERE templateName = ? AND roleName = ? AND ownerID = ?",
        (template_name, role_name, owner_id)
      )
      await db.commit()
      if cursor.rowcount == 0:
        return False
      else:
        logger.info(f"[DB] Removed role from template: {role_name} from {template_name} by {owner_id}")
        return True

  async def get_templates_by_owner(
    self,
    user_id:int
  ):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT * FROM RaidTemplates WHERE ownerID = ?",
        (user_id, )
      )
      return await cursor.fetchall()

  async def add_raid(
    self,
    leader_id: int,
    template_name: str,
    title: str,
    raid_time: datetime,
    message_id: int,
    channel_id: int
  ) -> int:
    async with aiosqlite.connect(self.db_path) as db:
      raid_time_str = raid_time.isoformat(sep=" ")
      cursor = await db.execute(
        "INSERT INTO Raids (leaderID, templateName, title, raidTime, messageID, channelID) VALUES (?, ?, ?, ?, ?, ?)",
        (leader_id, template_name, title, raid_time_str, message_id, channel_id)
      )
      await db.commit()
      logger.info(f"[DB] Raid created: {template_name} by {leader_id}")
      return cursor.lastrowid

  async def signup_user(
    self,
    user_id: int,
    raid_id: int,
    role_name: str,
  ) -> bool:
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT roleName FROM Signups WHERE raidID = ? AND userID = ?",
        (raid_id, user_id)
      )
      existing = await cursor.fetchone()

      if existing:
        await db.execute(
          "UPDATE Signups SET roleName = ? WHERE raidID = ? AND userID = ?",
          (role_name, raid_id, user_id)
        )
        await db.commit()
        logger.info(f"[DB] User signup updated: {user_id} from {raid_id}")
        return False
      else:
        cursor = await db.execute("SELECT COUNT(*) FROM Signups WHERE raidID = ?", (raid_id,))
        row = await cursor.fetchone()
        last_place = (row[0] or 0) + 1
        await db.execute(
          "INSERT INTO Signups (userID, raidID, roleName, signupRank) VALUES (?, ?, ?, ?)",
          (user_id, raid_id, role_name, last_place)
        )
        await db.commit()
        logger.info(f"[DB] User signup: {user_id} to {raid_id}")
        return True

  async def get_signups(self, raid_id: int) -> List[Tuple[int, str, str, int]]:
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "SELECT userID, roleName, signupTime, signupRank FROM Signups WHERE raidID = ? ORDER BY signupRank ASC",
        (raid_id,)
      )
      return await cursor.fetchall()

  async def remove_raid(self, raid_id: int) -> bool:
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute("DELETE FROM Signups WHERE raidID = ?", (raid_id,))
      cursor = await db.execute("DELETE FROM Raids WHERE raidID = ?", (raid_id,))
      await db.commit()
      if cursor.rowcount == 0:
        logger.warning(f"[DB] Raid not found to be removed: {raid_id}")
        return False
      else:
        logger.info(f"[DB] Raid and Signups removed: {raid_id}")
        return True

  async def clean_expired_raids(self):
    async with aiosqlite.connect(self.db_path) as db:
      logger.info("[~] Running raid DB cleanup...")
      now = datetime.now()
      cursor = await db.execute("SELECT raidID, messageID, channelID FROM Raids WHERE raidTime < ?", (now,))
      expired_raids = await cursor.fetchall()
      messages_infos = []

      for raid in expired_raids:
        raid_id, message_id, channel_id = raid
        await db.execute("DELETE FROM Signups WHERE raidID = ?", (raid_id,))
        await db.execute("DELETE FROM Raids WHERE raidID = ?", (raid_id,))
        await db.commit()
        messages_infos.append((message_id, channel_id))
        logger.info(f"[~] raid {raid_id} deleted")
      logger.info("[OK] Cleanup completed")
      return messages_infos
