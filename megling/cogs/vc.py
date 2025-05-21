import discord
import sqlite3
from discord.ext import commands

# voice.db:
# GuildChannels(guildID, channelID)
# VoiceChannels(channelID, guildID, ownerID, locked, hidden)
# UserSettings(userID, channelName, channelLimit)


class vc(commands.Cog):
  def __init__(self, bot):
    self.bot = bot
    print("SQLite checkup...")
    conn = sqlite3.connect("db/voice.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS GuildChannels (guildID INTEGER PRIMARY KEY, channelID INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS VoiceChannels (channelID INTEGER PRIMARY KEY, guildID INTEGER, ownerID INTEGER, locked BOOLEAN DEFAULT FALSE, hidden BOOLEAN DEFAULT FALSE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS UserSettings (userID INTEGER PRIMARY KEY, channelName TEXT, channelLimit INTEGER)")
    conn.commit()
    conn.close()
    print("[OK] SQLite checkup completed")


  async def cleanup(self):
    conn = sqlite3.connect("db/voice.db")
    cursor = conn.cursor()
    print(f"Cleaning leftover channels...")
    cursor.execute("SELECT channelID FROM VoiceChannels")
    channels = cursor.fetchall()
    for (channel_id,) in channels:
      channel = self.bot.get_channel(channel_id)
      if channel and isinstance(channel, discord.VoiceChannel):
        try:
          await channel.delete(reason="Cleaning leftover voice channel")
          cursor.execute("DELETE FROM VoiceChannels WHERE channelID = ?", (channel_id,))
        except:
          print(f"[?!] Failed to clean leftover voice channel with id: {channel_id}")
    conn.commit()
    conn.close()
    print(f"[OK] Cleaned voice channels")


  @commands.Cog.listener() # don't work :(
  async def on_ready(self):
    print("ready")
    await self.cleanup()


  @commands.hybrid_command()
  @commands.is_owner()
  async def clean(self, ctx):
    await self.cleanup()


  @commands.hybrid_command()
  @commands.is_owner()
  async def setup(self, ctx, channel_name):
    conn = sqlite3.connect("db/voice.db")
    cursor = conn.cursor()
    try:
      channel = await ctx.guild.create_voice_channel(channel_name, category=None)
      cursor.execute("SELECT * FROM GuildChannels WHERE guildID = ?", (ctx.guild.id,))
      voice = cursor.fetchone()
      if voice is None:
        cursor.execute ("INSERT INTO GuildChannels (guildID, channelID) VALUES (?, ?)",(ctx.guild.id, channel.id))
        print("Voice: New guild channel entry")
      else:
        cursor.execute ("UPDATE GuildChannels SET channelID = ? WHERE guildID = ?",(channel.id, ctx.guild.id))
        print("Voice: Guild channel updated")
      conn.commit()
      conn.close()
      await ctx.channel.send("**:gear:  You are all setup and ready to go!**")
    except:
      await ctx.channel.send("**:interrobang:  Operation failed!**")


  @commands.Cog.listener()
  async def on_voice_state_update(self, member, before, after):
    conn = sqlite3.connect("db/voice.db")
    cursor = conn.cursor()
    guildID = member.guild.id
    cursor.execute("SELECT ChannelID FROM GuildChannels WHERE guildID = ?", (guildID,))
    voice = cursor.fetchone()
    if voice:
      voiceID = int(voice[0])
      try:
        if after.channel and after.channel.id == voiceID:
          cursor.execute("SELECT channelName, channelLimit FROM UserSettings WHERE userID = ?", (member.id,))
          settings = cursor.fetchone()
          name = settings[0] if settings else f"{member.name}'s channel"
          limit = int(settings[1]) if settings else 0
          channel = await member.guild.create_voice_channel(name, category=after.channel.category, user_limit=limit)
          await member.move_to(channel)
          cursor.execute("INSERT INTO VoiceChannels (channelID, guildID, ownerID, locked, hidden) VALUES (?, ?, ?, FALSE, FALSE)", (channel.id, guildID, member.id))
          conn.commit()
          def check(_, __, ___):
            return len(channel.members) == 0
          await self.bot.wait_for('voice_state_update', check=check)
          await channel.delete()
          cursor.execute('DELETE FROM VoiceChannels WHERE channelID=?', (channel.id,))
      except:
        pass
    conn.commit()
    conn.close()


  async def isChannelOwner(self, ctx)->bool:
    if ctx.author.voice.channel is None:
      return False
    conn = sqlite3.connect("db/voice.db")
    cursor = conn.cursor()
    cursor.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (ctx.author.voice.channel.id,))
    owner_id = cursor.fetchone()
    conn.close()
    return owner_id and owner_id[0] == ctx.author.id


  @commands.hybrid_command()
  async def claim(self, ctx):
    if ctx.author.voice is None or ctx.author.voice.channel is None:
      await ctx.channel.send("**:interrobang:  You are not connected to any voice channel.**")
    else:
      conn = sqlite3.connect("db/voice.db")
      cursor = conn.cursor()
      cursor.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (ctx.author.voice.channel.id,))
      owner_id = cursor.fetchone()
      if owner_id:
        owner_id = owner_id[0]
        if owner_id == ctx.author.id:
          await ctx.channel.send("**:crown:  You already are owner of this channel.**")
        elif any(member.id == owner_id for member in ctx.author.voice.channel.members):
          await ctx.channel.send("**:interrobang:  Channel owner is still present.**")
        else:
          cursor.execute("UPDATE VoiceChannels SET ownerID = ? WHERE channelID = ?", (ctx.author.id, ctx.author.voice.channel.id))
          conn.commit()
          await ctx.channel.send("**:crown:  You are now owner of the channel.**")
      else:
        await ctx.channel.send("**:interrobang:  There is no ownership to be claimed in this channed**")
      conn.close()


  @commands.hybrid_command()
  async def lock(self, ctx):
    if ctx.author.voice is None:
      await ctx.channel.send("**:interrobang:  You are not connected to any voice channel.**")
    elif await self.isChannelOwner(ctx):
      channel = ctx.author.voice.channel
      try:
        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.connect = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
        await ctx.send("**:lock:  Your channel has been locked.**")
      except:
        await ctx.channel.send("**:interrobang:  Unexpected error**")
    else:
      await ctx.channel.send("**:interrobang:  You are not owner of the channel.**")


  @commands.hybrid_command()
  async def unlock(self, ctx):
    if ctx.author.voice is None:
      await ctx.channel.send("**:interrobang:  You are not connected to any voice channel.**")
    elif await self.isChannelOwner(ctx):
      channel = ctx.author.voice.channel
      try:
        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.connect = True
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
        await ctx.send("**:unlock:  Your channel has been unlocked.**")
      except:
        await ctx.channel.send("**:interrobang:  Unexpected error**")
    else:
      await ctx.channel.send("**:interrobang:  You are not owner of the channel.**")


  @commands.hybrid_command()
  async def limit(self, ctx, limit=0):
    if ctx.author.voice is None:
      await ctx.channel.send("**:interrobang:  You are not connected to any voice channel.**")
    elif await self.isChannelOwner(ctx):
      try:
        await ctx.author.voice.channel.edit(user_limit = limit)
        if limit == 0:
          await ctx.channel.send(f"**:tada:  Channel user limit has been removed.**")
        else:
          await ctx.channel.send(f"**:tickets:  Channel user limit has been set to {limit}.**")
      except:
        await ctx.channel.send("**:interrobang:  Unexpected error**")
    else:
      await ctx.channel.send("**:interrobang:  You are not owner of the channel.**")


  @commands.hybrid_command()
  async def hide(self, ctx):
    if ctx.author.voice is None:
      await ctx.channel.send("**:interrobang:  You are not connected to any voice channel.**")
    elif await self.isChannelOwner(ctx):
      channel = ctx.author.voice.channel
      try:
        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.send("**:dotted_line_face:  Your channel is now invisible.**")
      except:
        await ctx.channel.send("**:interrobang:  Unexpected error**")
    else:
      await ctx.channel.send("**:interrobang:  You are not owner of the channel.**")

  @commands.hybrid_command()
  async def reveal(self, ctx):
    if ctx.author.voice is None:
      await ctx.channel.send("**:interrobang:  You are not connected to any voice channel.**")
    elif await self.isChannelOwner(ctx):
      channel = ctx.author.voice.channel
      try:
        await channel.set_permissions(ctx.guild.default_role, view_channel=True)
        await ctx.send("**:camera:  Your channel is now visible.**")
      except:
        await ctx.channel.send("**:interrobang:  Unexpected error**")
    else:
      await ctx.channel.send("**:interrobang:  You are not owner of the channel.**")


  @commands.hybrid_command()
  async def set(self, ctx, name:str, limit=0):
    with sqlite3.connect("db/voice.db") as conn:
      cursor = conn.cursor()
      cursor.execute("SELECT * FROM UserSettings WHERE userID = ?", (ctx.author.id,))
      if cursor.fetchone():
        cursor.execute ("UPDATE UserSettings SET channelName = ?, channelLimit = ? WHERE userdID = ?",(name, limit, ctx.author.id))
        await ctx.channel.send("**:gear:  Default channel settings changed.**")
      else:
        cursor.execute ("INSERT INTO UserSettings (userID, channelName, channelLimit) VALUES (?, ?, ?) ",(ctx.author.id, name, limit))
        await ctx.channel.send("**:gear:  Default channel settings set!**")


  # @commands.Cog.hybrid_command()
  # async def reset(self, ctx, name:str, limit:int):
  #   pass


async def setup(bot):
  print("Loading vc...")
  await bot.add_cog(vc(bot))
  print("[OK] vc loaded")
