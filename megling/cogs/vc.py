import sqlite3
from discord.ext import commands
from discord import app_commands, Interaction, VoiceChannel
from discord.abc import PrivateChannel


# voice.db:
# GuildChannels(guildID, channelID)
# VoiceChannels(channelID, guildID, ownerID)
# UserSettings(userID, channelName, channelLimit)


def is_owner_check(interaction: Interaction):
    return interaction.user.id == 454929922108948480

def get_connected_voice_channel(interaction: Interaction):
    return interaction.user.voice.channel if interaction.user.voice else None

class VCSettingsGroup(app_commands.Group):
  def __init__(self, bot: commands.Bot):
    super().__init__(name="settings", description="Voice creator settings")
    self.bot = bot


  @app_commands.command(name="set", description="Defaul channel settings")
  async def set(self, interaction:Interaction, name:str, limit:int=0):
    with sqlite3.connect("db/voice.db") as conn:
      cursor = conn.cursor()
      cursor.execute("SELECT * FROM UserSettings WHERE userID = ?", (interaction.user.id,))
      if cursor.fetchone():
        cursor.execute ("UPDATE UserSettings SET channelName = ?, channelLimit = ? WHERE userID = ?",(name, limit, interaction.user.id))
        conn.commit()
        await interaction.response.send_message(":gear:  **Default channel settings changed**")
      else:
        cursor.execute ("INSERT INTO UserSettings (userID, channelName, channelLimit) VALUES (?, ?, ?)",(interaction.user.id, name, limit))
        await interaction.response.send_message(":gear:  **Default channel settings set!**")


  @app_commands.command(name="reset", description="Reset default channel settings")
  async def reset(self, interaction):
    with sqlite3.connect("db/voice.db") as conn:
      cursor = conn.cursor()
      cursor.execute("SELECT * FROM UserSettings WHERE userID = ?", (interaction.user.id,))
      if cursor.fetchone():
        cursor.execute ("DELETE FROM UserSettings WHERE userID = ?",(interaction.user.id,))
        conn.commit()
        await interaction.response.send_message(":wastebasket:  **Default channel settings reseted**")
      else:
        await interaction.response.send_message(":interrobang:  **There were no settings to reset**")



class VCGroup(app_commands.Group):
  def __init__(self, bot: commands.Bot):
    super().__init__(name="vc", description="Voice creator commands")
    self.bot = bot
    self.add_command(VCSettingsGroup(bot))

  async def isChannelOwner(self, interaction)->bool:
    if not interaction.user.voice or not interaction.user.voice.channel:
      return False
    with sqlite3.connect("db/voice.db") as conn:
      cursor = conn.cursor()
      cursor.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (interaction.user.voice.channel.id,))
      owner_id = cursor.fetchone()
      return owner_id and owner_id[0] == interaction.user.id


  async def cleanup(self):
    with sqlite3.connect("db/voice.db") as conn:
      cursor = conn.cursor()
      print(f"Cleaning leftover channels...")
      cursor.execute("SELECT channelID FROM VoiceChannels")
      channels = cursor.fetchall()
      for (channel_id,) in channels:
        channel = self.bot.get_channel(channel_id)
        if channel and isinstance(channel, VoiceChannel):
          try:
            await channel.delete(reason="Cleaning leftover voice channel")
          except Exception as e:
            print(f"[?!] Failed to clean leftover voice channel with id: {channel_id}, Exception: {e}")
          cursor.execute("DELETE FROM VoiceChannels WHERE channelID = ?", (channel_id,))
          conn.commit()
      print(f"[OK] Cleaned voice channels")


  @app_commands.command(name="clean", description="Clear leftover voice channels")
  @app_commands.check(is_owner_check)
  async def clean(self, interaction):
    await interaction.response.send_message(":wastebasket:  **Cleaning leftover voice channels**")
    await self.cleanup()


  @app_commands.command(name="setup", description="Setup voice creator")
  @app_commands.check(is_owner_check)
  async def setup(self, interaction:Interaction, channel_name:str="Voice creator"):
    with sqlite3.connect("db/voice.db") as conn:
      cursor = conn.cursor()
      try:
        channel = await interaction.guild.create_voice_channel(channel_name, category=None)
        cursor.execute("SELECT channelID FROM GuildChannels WHERE guildID = ?", (interaction.guild.id,))
        old_channel_id = cursor.fetchone()
        if old_channel_id is None:
          cursor.execute ("INSERT INTO GuildChannels (guildID, channelID) VALUES (?, ?)",(interaction.guild.id, channel.id))
          conn.commit()
        else:
          old_channel = self.bot.get_channel(old_channel_id[0])
          if old_channel and old_channel != PrivateChannel:
            await old_channel.delete(reason="Delete old voice creator")
          cursor.execute ("UPDATE GuildChannels SET channelID = ? WHERE guildID = ?",(channel.id, interaction.guild.id))
          conn.commit()
        await interaction.response.send_message(":gear:  **You are all setup and ready to go!**")
      except Exception as e:
        print(f"[?!] Failed to add/update new guild voice creator channel, Exception : {e}")
        await interaction.response.send_message(":interrobang:  **Operation failed!**")


  @app_commands.command(name="claim", description="Claim active channel if owner is gone")
  async def claim(self, interaction):
    if interaction.user.voice is None or interaction.user.voice.channel is None:
      await interaction.response.send_message(":interrobang:  **You are not connected to any voice channel**")
    else:
      with sqlite3.connect("db/voice.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (interaction.user.voice.channel.id,))
        owner_id = cursor.fetchone()
        if owner_id:
          owner_id = owner_id[0]
          if owner_id == interaction.user.id:
            await interaction.response.send_message(":crown:  **You already are owner of this channel**")
          elif any(member.id == owner_id for member in interaction.user.voice.channel.members):
            await interaction.response.send_message(":interrobang:  **Channel owner is still present**")
          else:
            cursor.execute("UPDATE VoiceChannels SET ownerID = ? WHERE channelID = ?", (interaction.user.id, interaction.user.voice.channel.id))
            conn.commit()
            await interaction.response.send_message(":crown:  **You are now owner of the channel**")
        else:
          await interaction.response.send_message(":interrobang:  **There is no ownership to be claimed in this channel**")


  @app_commands.command(name="lock", description="Lock active channel")
  async def lock(self, interaction):
    if interaction.user.voice is None:
      await interaction.response.send_message(":interrobang:  **You are not connected to any voice channel**")
    elif await self.isChannelOwner(interaction):
      try:
        await interaction.user.voice.channel.edit(connect = False)
        await interaction.response.send_message(":lock:  **Your channel has been locked**")
      except Exception as e:
        print(f"[?!] Failed to lock channel, Exception : {e}")
        await interaction.response.send_message(":interrobang:  **Unexpected error**")
    else:
      await interaction.response.send_message(":interrobang:  **You are not owner of the channel**")


  @app_commands.command(name="unlock", description="Unlock active channel")
  async def unlock(self, interaction):
    if interaction.user.voice is None:
      await interaction.response.send_message(":interrobang:  **You are not connected to any voice channel**")
    elif await self.isChannelOwner(interaction):
      try:
        await interaction.user.voice.channel.edit(connect = True)
        await interaction.response.send_message(":unlock:  **Your channel has been unlocked**")
      except Exception as e:
        print(f"[?!] Failed to unlock channel, Exception : {e}")
        await interaction.response.send_message(":interrobang:  **Unexpected error**")
    else:
      await interaction.response.send_message(":interrobang:  **You are not owner of the channel**")


  @app_commands.command(name="limit", description="Limit active channel")
  async def limit(self, interaction:Interaction, limit:int=0):
    if interaction.user.voice is None:
      await interaction.response.send_message(":interrobang:  **You are not connected to any voice channel**")
    elif await self.isChannelOwner(interaction):
      try:
        await interaction.user.voice.channel.edit(user_limit = limit)
        if limit == 0:
          await interaction.response.send_message(f":tada:  **Channel user limit has been removed**")
        else:
          await interaction.response.send_message(f":tickets:  **Channel user limit has been set to {limit}**")
      except Exception as e:
        print(f"[?!] Failed to limit channel, Exception : {e}")
        await interaction.response.send_message(":interrobang:  **Unexpected error**")
    else:
      await interaction.response.send_message(":interrobang:  **You are not owner of the channel**")


  @app_commands.command(name="hide", description="Hide active channel")
  async def hide(self, interaction):
    if interaction.user.voice is None:
      await interaction.response.send_message(":interrobang:  **You are not connected to any voice channel**")
    elif await self.isChannelOwner(interaction):
      channel = interaction.user.voice.channel
      try:
        await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(":dotted_line_face:  **Your channel is now invisible**")
      except Exception as e:
        print(f"[?!] Failed to hide channel, Exception : {e}")
        await interaction.response.send_message(":interrobang:  **Unexpected error**")
    else:
      await interaction.response.send_message(":interrobang:  **You are not owner of the channel**")


  @app_commands.command(name="reveal", description="Reveal active channel")
  async def reveal(self, interaction):
    if interaction.user.voice is None:
      await interaction.response.send_message(":interrobang:  **You are not connected to any voice channel**")
    elif await self.isChannelOwner(interaction):
      channel = interaction.user.voice.channel
      try:
        await channel.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message(":camera:  **Your channel is now visible**")
      except Exception as e:
        print(f"[?!] Failed to reveal channel, Exception : {e}")
        await interaction.response.send_message(":interrobang:  **Unexpected error**")
    else:
      await interaction.response.send_message(":interrobang:  **You are not owner of the channel**")


  @app_commands.command(name="rename", description="Rename active channel")
  async def rename(self, interaction:Interaction, name:str):
    if interaction.user.voice is None:
      await interaction.response.send_message(":interrobang:  **You are not connected to any voice channel**")
    elif await self.isChannelOwner(interaction):
      try:
        await interaction.user.voice.channel.edit(name = name)
        await interaction.response.send_message(f":pen_ballpoint:  **Channel has been renamed to {name}**")
      except Exception as e:
        print(f"[?!] Failed to rename channel, Exception : {e}")
        await interaction.response.send_message(":interrobang:  **Unexpected error**")
    else:
      await interaction.response.send_message(":interrobang:  **You are not owner of the channel**")



class VCCog(commands.Cog):
  def __init__(self, bot):
    self.bot = bot
    print("SQLite checkup...")
    with sqlite3.connect("db/voice.db") as conn:
      cursor = conn.cursor()
      cursor.execute("CREATE TABLE IF NOT EXISTS GuildChannels (guildID INTEGER PRIMARY KEY, channelID INTEGER)")
      cursor.execute("CREATE TABLE IF NOT EXISTS VoiceChannels (channelID INTEGER PRIMARY KEY, guildID INTEGER, ownerID INTEGER)")
      cursor.execute("CREATE TABLE IF NOT EXISTS UserSettings (userID INTEGER PRIMARY KEY, channelName TEXT, channelLimit INTEGER)")
      conn.commit()
      print("[OK] SQLite checkup completed")
    self.bot.tree.add_command(VCGroup(bot))


  @commands.Cog.listener() # don't work :(
  async def on_ready(self):
    # await self.cleanup()
    pass


  @commands.Cog.listener()
  async def on_voice_state_update(self, member, before, after):
    with sqlite3.connect("db/voice.db") as conn:
      cursor = conn.cursor()
      guild_id = member.guild.id
      cursor.execute("SELECT ChannelID FROM GuildChannels WHERE guildID = ?", (guild_id,))
      voice = cursor.fetchone()
      if voice:
        voiceID = voice[0]
        try:
          if after.channel and after.channel.id == voiceID:
            cursor.execute("SELECT channelName, channelLimit FROM UserSettings WHERE userID = ?", (member.id,))
            settings = cursor.fetchone()
            name = settings[0] if settings else f"{member.name}'s channel"
            limit = int(settings[1]) if settings else 0
            channel = await member.guild.create_voice_channel(name, category=after.channel.category, user_limit=limit)
            await member.move_to(channel)
            cursor.execute("INSERT INTO VoiceChannels (channelID, guildID, ownerID) VALUES (?, ?, ?)", (channel.id, guild_id, member.id))
            conn.commit()
            def check(_, __, ___):
              return len(channel.members) == 0
            await self.bot.wait_for('voice_state_update', check=check)
            await channel.delete()
            cursor.execute('DELETE FROM VoiceChannels WHERE channelID=?', (channel.id,))
            conn.commit()
        except Exception as e:
          print(f"[?!] Failed to voice state update from voice creator, Exception : {e}")



async def setup(bot):
  print("Loading vc...")
  await bot.add_cog(VCCog(bot))
  print("[OK] vc loaded")
