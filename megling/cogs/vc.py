import aiosqlite

from discord.ext import commands
from discord import ApplicationContext, VoiceChannel, SlashCommandGroup, Bot
from discord.abc import PrivateChannel

# voice.db:
# GuildChannels(guildID, channelID)
# VoiceChannels(channelID, guildID, ownerID)
# UserSettings(userID, channelName, channelLimit)


def get_connected_voice_channel(ctx: ApplicationContext):
    return ctx.user.voice.channel if ctx.user.voice else None


async def isChannelOwner(ctx: ApplicationContext)->bool:
  if not ctx.user.voice or not ctx.user.voice.channel:
    return False
  async with aiosqlite.connect("db/voice.db") as db:
    async with db.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (ctx.user.voice.channel.id,)) as cursor:
      owner_id = await cursor.fetchone()
      return owner_id and owner_id[0] == ctx.user.id


async def get_own_channel(ctx: ApplicationContext):
  if not ctx.user.voice:
    return None
  channel = ctx.user.voice.channel
  async with aiosqlite.connect("db/voice.db") as db:
    async with db.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (channel.id,)) as cursor:
      owner = await cursor.fetchone()
      if owner and owner[0] == ctx.user.id:
        return channel
  return None


async def cleanup(bot: Bot):
  async with aiosqlite.connect("db/voice.db") as db:
    print(f"Cleaning leftover channels...")
    async with db.execute("SELECT channelID FROM VoiceChannels") as cursor:
      channels = await cursor.fetchall()
      for (channel_id,) in channels:
        channel = bot.get_channel(channel_id)
        if channel and isinstance(channel, VoiceChannel):
          try:
            await channel.delete(reason="Cleaning leftover voice channel")
          except Exception as e:
            print(f"[?!] Failed to clean leftover voice channel with id: {channel_id}, Exception: {e}")
          await db.execute("DELETE FROM VoiceChannels WHERE channelID = ?", (channel_id,))
          await db.commit()
      print(f"[OK] Cleaned voice channels")




class VCCog(commands.Cog):
  def __init__(self, bot):
    self.bot = bot


  @commands.Cog.listener()
  async def on_voice_state_update(self, member, before, after):
    async with aiosqlite.connect("db/voice.db") as db:
      guild_id = member.guild.id
      async with db.execute("SELECT ChannelID FROM GuildChannels WHERE guildID = ?", (guild_id,)) as cursor:
        voice = await cursor.fetchone()
        if voice:
          voice_id = voice[0]
          try:
            if after.channel and after.channel.id == voice_id:
              async with db.execute("SELECT channelName, channelLimit FROM UserSettings WHERE userID = ?", (member.id,)) as cursor:
                settings = await cursor.fetchone()
                name = settings[0] if settings else f"{member.name}'s channel"
                limit = int(settings[1]) if settings else 0
                channel = await member.guild.create_voice_channel(name, category=after.channel.category, user_limit=limit)
                await member.move_to(channel)
                await db.execute("INSERT INTO VoiceChannels (channelID, guildID, ownerID) VALUES (?, ?, ?)", (channel.id, guild_id, member.id))
                await db.commit()
                def check(*args):
                  return len(channel.members) == 0
                await self.bot.wait_for('voice_state_update', check=check)
                await channel.delete()
                await db.execute('DELETE FROM VoiceChannels WHERE channelID=?', (channel.id,))
                await db.commit()
          except Exception as e:
            print(f"[?!] Failed to voice state update from voice creator, Exception : {e}")


  vc = SlashCommandGroup("vc", description="Voice creator")


  @vc.command(name="clean", description="Clear leftover voice channels")
  @commands.is_owner()
  async def clean(self, ctx):
    await ctx.respond(":wastebasket:  **Cleaning leftover voice channels**")
    await cleanup(self.bot)


  @vc.command(name="setup", description="Setup voice creator")
  @commands.is_owner()
  async def setup(self, ctx: ApplicationContext, channel_name:str="Voice creator"):
    async with aiosqlite.connect("db/voice.db") as db:
      try:
        channel = await ctx.guild.create_voice_channel(channel_name, category=None)
        async with db.execute("SELECT channelID FROM GuildChannels WHERE guildID = ?", (ctx.guild.id,)) as cursor:
          old_channel_id = await cursor.fetchone()
          if old_channel_id is None:
            await db.execute ("INSERT INTO GuildChannels (guildID, channelID) VALUES (?, ?)",(ctx.guild.id, channel.id))
            await db.commit()
          else:
            old_channel = self.bot.get_channel(old_channel_id[0])
            if old_channel and old_channel != PrivateChannel:
              await old_channel.delete(reason="Delete old voice creator")
            await db.execute ("UPDATE GuildChannels SET channelID = ? WHERE guildID = ?",(channel.id, ctx.guild.id))
            await db.commit()
          await ctx.respond(":gear:  **You are all setup and ready to go!**")
      except Exception as e:
        print(f"[?!] Failed to add/update new guild voice creator channel, Exception : {e}")
        await ctx.respond(":interrobang:  **Operation failed!**")


  @vc.command(name="claim", description="Claim active channel if owner is gone")
  async def claim(self, ctx: ApplicationContext):
    if ctx.user.voice is None or ctx.user.voice.channel is None:
      await ctx.respond(":interrobang:  **You are not connected to any voice channel**")
    else:
      async with aiosqlite.connect("db/voice.db") as db:
        async with db.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (ctx.user.voice.channel.id,)) as cursor:
          owner_id = await cursor.fetchone()
          if owner_id:
            owner_id = owner_id[0]
            if owner_id == ctx.user.id:
              await ctx.respond(":crown:  **You already are owner of this channel**")
            elif any(member.id == owner_id for member in ctx.user.voice.channel.members):
              await ctx.respond(":interrobang:  **Channel owner is still present**")
            else:
              await db.execute("UPDATE VoiceChannels SET ownerID = ? WHERE channelID = ?", (ctx.user.id, ctx.user.voice.channel.id))
              await db.commit()
              await ctx.respond(":crown:  **You are now owner of the channel**")
          else:
            await ctx.respond(":interrobang:  **There is no ownership to be claimed in this channel**")


  @vc.command(name="lock", description="Lock active channel")
  async def lock(self, ctx: ApplicationContext):
    if ctx.user.voice is None:
      await ctx.respond(":interrobang:  **You are not connected to any voice channel**")
    elif await isChannelOwner(ctx):
      try:
        await ctx.user.voice.channel.edit(connect = False)
        await ctx.respond(":lock:  **Your channel has been locked**")
      except Exception as e:
        print(f"[?!] Failed to lock channel, Exception : {e}")
        await ctx.respond(":interrobang:  **Unexpected error**")
    else:
      await ctx.respond(":interrobang:  **You are not owner of the channel**")


  @vc.command(name="unlock", description="Unlock active channel")
  async def unlock(self, ctx: ApplicationContext):
    if ctx.user.voice is None:
      await ctx.respond(":interrobang:  **You are not connected to any voice channel**")
    elif await isChannelOwner(ctx):
      try:
        await ctx.user.voice.channel.edit(connect = True)
        await ctx.respond(":unlock:  **Your channel has been unlocked**")
      except Exception as e:
        print(f"[?!] Failed to unlock channel, Exception : {e}")
        await ctx.respond(":interrobang:  **Unexpected error**")
    else:
      await ctx.respond(":interrobang:  **You are not owner of the channel**")


  @vc.command(name="limit", description="Limit active channel")
  async def limit(self, ctx: ApplicationContext, limit: int=0):
    if ctx.user.voice is None:
      await ctx.respond(":interrobang:  **You are not connected to any voice channel**")
    elif await isChannelOwner(ctx):
      try:
        await ctx.user.voice.channel.edit(user_limit = limit)
        if limit == 0:
          await ctx.respond(f":tada:  **Channel user limit has been removed**")
        else:
          await ctx.respond(f":tickets:  **Channel user limit has been set to {limit}**")
      except Exception as e:
        print(f"[?!] Failed to limit channel, Exception : {e}")
        await ctx.respond(":interrobang:  **Unexpected error**")
    else:
      await ctx.respond(":interrobang:  **You are not owner of the channel**")


  @vc.command(name="hide", description="Hide active channel")
  async def hide(self, ctx: ApplicationContext):
    if ctx.user.voice is None:
      await ctx.respond(":interrobang:  **You are not connected to any voice channel**")
    elif await isChannelOwner(ctx):
      channel = ctx.user.voice.channel
      try:
        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.respond(":dotted_line_face:  **Your channel is now invisible**")
      except Exception as e:
        print(f"[?!] Failed to hide channel, Exception : {e}")
        await ctx.respond(":interrobang:  **Unexpected error**")
    else:
      await ctx.respond(":interrobang:  **You are not owner of the channel**")


  @vc.command(name="reveal", description="Reveal active channel")
  async def reveal(self, ctx: ApplicationContext):
    if ctx.user.voice is None:
      await ctx.respond(":interrobang:  **You are not connected to any voice channel**")
    elif await isChannelOwner(ctx):
      channel = ctx.user.voice.channel
      try:
        await channel.set_permissions(ctx.guild.default_role, view_channel=True)
        await ctx.respond(":camera:  **Your channel is now visible**")
      except Exception as e:
        print(f"[?!] Failed to reveal channel, Exception : {e}")
        await ctx.respond(":interrobang:  **Unexpected error**")
    else:
      await ctx.respond(":interrobang:  **You are not owner of the channel**")


  @vc.command(name="rename", description="Rename active channel")
  async def rename(self, ctx: ApplicationContext, name:str):
    if ctx.user.voice is None:
      await ctx.respond(":interrobang:  **You are not connected to any voice channel**")
    elif await isChannelOwner(ctx):
      try:
        await ctx.user.voice.channel.edit(name = name)
        await ctx.respond(f":pen_ballpoint:  **Channel has been renamed to {name}**")
      except Exception as e:
        print(f"[?!] Failed to rename channel, Exception : {e}")
        await ctx.respond(":interrobang:  **Unexpected error**")
    else:
      await ctx.respond(":interrobang:  **You are not owner of the channel**")


  settings = vc.create_subgroup("settings", description="Voice creator settings")


  @settings.command(name="set", description="Defaul channel settings")
  async def set(self, ctx: ApplicationContext, name:str, limit:int=0):
    async with aiosqlite.connect("db/voice.db") as db:
      async with db.execute("SELECT * FROM UserSettings WHERE userID = ?", (ctx.user.id,)) as cursor:
        if await cursor.fetchone():
          await db.execute ("UPDATE UserSettings SET channelName = ?, channelLimit = ? WHERE userID = ?",(name, limit, ctx.user.id))
          await ctx.respond(":gear:  **Default channel settings changed**")
        else:
          await db.execute ("INSERT INTO UserSettings (userID, channelName, channelLimit) VALUES (?, ?, ?)",(ctx.user.id, name, limit))
          await ctx.respond(":gear:  **Default channel settings set!**")
        await db.commit()


  @settings.command(name="reset", description="Reset default channel settings")
  async def reset(self, ctx):
    async with aiosqlite.connect("db/voice.db") as db:
      async with db.execute("SELECT * FROM UserSettings WHERE userID = ?", (ctx.user.id,)) as cursor:
        if await cursor.fetchone():
          await db.execute ("DELETE FROM UserSettings WHERE userID = ?",(ctx.user.id,))
          await db.commit()
          await ctx.respond(":wastebasket:  **Default channel settings reseted**")
        else:
          await ctx.respond(":interrobang:  **There were no settings to reset**")



def setup(bot):
  print("[~~] Loading vc...")
  bot.add_cog(VCCog(bot))
  print("[OK] vc loaded")

  # print("SQLite checkup...")
  # async with aiosqlite.connect("db/voice.db") as db:
  #   await db.execute("CREATE TABLE IF NOT EXISTS GuildChannels (guildID INTEGER PRIMARY KEY, channelID INTEGER)")
  #   await db.execute("CREATE TABLE IF NOT EXISTS VoiceChannels (channelID INTEGER PRIMARY KEY, guildID INTEGER, ownerID INTEGER)")
  #   await db.execute("CREATE TABLE IF NOT EXISTS UserSettings (userID INTEGER PRIMARY KEY, channelName TEXT, channelLimit INTEGER)")
  #   await db.commit()
  #   print("[OK] SQLite checkup completed")
  #
  # await cleanup(bot)
