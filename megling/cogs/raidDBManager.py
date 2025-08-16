import aiosqlite
from datetime import datetime
from megling.logsetup import setupLogger

logger = setupLogger(__name__)


# raid.db
# RaidTemplates(templateName, url, description, image, thumbnail, ownerID)
# TemplateRoles(templateName, roleName, roleIcon, maxSlots)
# Raids(raidID, leaderID, templateName, title, raidTime, number)
# Signups(signupID, userID, raidID, roleName, note, signupTime, signupRank)


class RaidDB:
  def __init__(self, db_path: str = "db/raid.db"):
    self.db_path = db_path

  async def checkup(self):
    async with aiosqlite.connect(self.db_path) as db:
      logger.info("[~~] SQLite raid.db checkup...")
      await db.execute("""
CREATE TABLE IF NOT EXISTS RaidTemplates (
  templateName TEXT PRIMARY KEY,
  url TEXT,
  description TEXT,
  image TEXT,
  thumbnail TEXT
  ownerID INTERGER,
);
      """)
      await db.execute("""
CREATE TABLE IF NOT EXISTS TemplateRoles (
  templateName TEXT,
  roleName TEXT,
  roleIcon TEXT,
  maxSlots INTEGER,
  PRIMARY KEY (templateName, roleName),
  FOREIGN KEY (templateName) REFERENCES RaidTemplates(templateName)
);
      """)
      await db.execute("""
CREATE TABLE IF NOT EXISTS Raids (
  raidID INTEGER PRIMARY KEY AUTOINCREMENT,
  leaderID INTEGER NOT NULL,
  templateName TEXT NOT NULL,
  title TEXT NOT NULL,
  raidTime DATETIME NOT NULL,
  number INTEGER,
  FOREIGN KEY (templateName) REFERENCES RaidTemplates(templateName)
);
      """)
      await db.execute("""
CREATE TABLE IF NOT EXISTS Signups (
  signupID INTEGER PRIMARY KEY AUTOINCREMENT,
  userID INTEGER NOT NULL,
  raidID INTEGER NOT NULL,
  roleName TEXT,
  note TEXT,
  signupTime DATETIME DEFAULT CURRENT_TIMESTAMP,
  signupRank INTEGER,
  FOREIGN KEY (raidID) REFERENCES Raids(raidID),
  UNIQUE(userID, raidID)
);
      """)
      await db.commit()
      logger.info("[OK] SQLite raid.db checkup completed")


  async def get_raid(self, raidID: int):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute("SELECT * FROM Raids WHERE raidID = ?", (raidID,))
      return await cursor.fetchone()


  async def get_template(self, templateName):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute("SELECT * FROM RaidTemplates WHERE templateName = ?", (templateName,))
      return await cursor.fetchone()


   async def get_template_roles(self, templateName):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute("SELECT roleName, roleIcon, maxSlots FROM TemplateRoles WHERE templateName = ?", (templateName,))
      return await cursor.fetchall()


  # TODO create roles
  async def create_template(self, templateName:str, url:str|None, description:str|None, image:str|None, thumbnail:str|None, ownerID:int|None):
    async def with aiosqlite.connect(self.db_path) sa db:
      await db.execute("INSERT INTO RaidTemplates (templateName, url, description, image, thumbnail, ownerID) VALUES (?, ?, ?, ?, ?, ?)", (templateName, url, description, image, thumbnail, ownerID))


  async def add_raid(self, leaderId: int, templateName: str, title: str, raidTime: datetime) -> int:
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute(
        "INSERT INTO Raids (leaderID, templateName, title, raidTime, number) VALUES (?, ?, ?, ?, 0)",
        (leaderId, templateName, title, raidTime.isoformat())
      )
      await db.commit()
      return cursor.lastrowid


  async def signup_user(self, userID: int, raidID: int, roleName: str, note: str = "") -> Bool:
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute("SELECT roleName FROM Signups WHERE raidID = ? AND userID = ?", (raidID, userID))
      signedRoleName = await cursor.fetchone()
      if signedRoleName:
        await db.execute ("UPDATE Signups SET roleName = ? WHERE raidID = ? AND userID = ?",(roleName, raidID, userID))
        await db.commit()
        return False
      else:
        raidInfo = await self.get_raid(raidID)
        lastPlace = raidInfo[5]+1
        await db.execute(
          "INSERT INTO Signups (userID, raidID, roleName, note, signupRank) VALUES (?, ?, ?, ?, ?)",
          (userID, raidID, roleName, note, lastPlace)
        )
        await db.execute ("UPDATE Raids SET number = ? WHERE raidID = ?",(lastPlace, raidID))
        await db.commit()
        return True


  async def get_signups(self, raid_id: int):
    async with aiosqlite.connect(self.db_path) as db:
      cursor = await db.execute("SELECT userID, roleName, note, signupTime, signupRank FROM Signups WHERE raidID = ? ORDER BY signupRank ASC", (raid_id,))
      rows = await cursor.fetchall()
      return rows
