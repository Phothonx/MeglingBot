import aiosqlite

from discord.ext import commands, tasks
from discord.ext.commands import CommandError, CheckFailure, guild_only, NoPrivateMessage
from discord import ApplicationContext, VoiceChannel, SlashCommandGroup, Bot
from megling.logsetup import setupLogger

logger = setupLogger(__name__)

# voice.db:
# GuildChannels(guildID, channelID)
# VoiceChannels(channelID, guildID, ownerID)
# UserSettings(userID, channelName, channelLimit)


def get_connected_voice_channel(ctx: ApplicationContext):
    return ctx.user.voice.channel if ctx.user.voice else None

class NotVoiceOwner(CheckFailure):
  pass

def is_voice_owner():
  async def predicate(ctx):
    channel = get_connected_voice_channel(ctx)
    if channel:
      async with aiosqlite.connect("db/voice.db") as db:
        async with db.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (channel.id,)) as cursor:
          owner_id = await cursor.fetchone()
          if bool(owner_id) and owner_id[0] == ctx.user.id:
            return True
    raise NotVoiceOwner()
  return commands.check(predicate)


class NotInVoiceChannel(CheckFailure):
  pass

def is_in_voice_channel():
  async def predicate(ctx):
    channel = get_connected_voice_channel(ctx)
    if channel:
      return True
    raise NotInVoiceChannel()
  return commands.check(predicate)


async def cleanup(bot: Bot):
  async with aiosqlite.connect("db/voice.db") as db:
    logger.info(f"[~~] Cleaning leftover channels...")
    async with db.execute("SELECT channelID FROM VoiceChannels") as cursor:
      channels = await cursor.fetchall()
      for (channel_id,) in channels:
        channel = await bot.fetch_channel(channel_id)
        if channel and isinstance(channel, VoiceChannel):
          await channel.delete(reason="Cleaning leftover voice channel")
          await db.execute("DELETE FROM VoiceChannels WHERE channelID = ?", (channel_id,))
          await db.commit()
      logger.info(f"[OK] Cleaned voice channels")




class VCCog(commands.Cog):
  def __init__(self, bot):
    self.bot = bot
    self.auto_clean.start()


  def cog_unload(self):
      self.printer.cancel()

  @tasks.loop(hours=1)
  async def auto_clean(self):
    await cleanup(self.bot)

  @auto_clean.before_loop
  async def first_clean(self):
    logger.info("[~~] SQLite checkup...")
    async with aiosqlite.connect("db/voice.db") as db:
      await db.execute("CREATE TABLE IF NOT EXISTS GuildChannels (guildID INTEGER PRIMARY KEY, channelID INTEGER)")
      await db.execute("CREATE TABLE IF NOT EXISTS VoiceChannels (channelID INTEGER PRIMARY KEY, guildID INTEGER, ownerID INTEGER)")
      await db.execute("CREATE TABLE IF NOT EXISTS UserSettings (userID INTEGER PRIMARY KEY, channelName TEXT, channelLimit INTEGER)")
      await db.commit()
      logger.info("[OK] SQLite checkup completed")


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
                def check(*_):
                  return len(channel.members) == 0
                await self.bot.wait_for('voice_state_update', check=check)
                await channel.delete()
                await db.execute('DELETE FROM VoiceChannels WHERE channelID=?', (channel.id,))
                await db.commit()
          except Exception as e:
            logger.error(f"[?!] Failed to voice state update from voice creator, Exception : {e}")


  vc = SlashCommandGroup("vc", description="Voice creator")


  @vc.command(name="clean", description="Clear leftover voice channels")
  @commands.is_owner()
  async def clean(self, ctx):
    await ctx.respond(":wastebasket:  **Cleaning leftover voice channels**")
    await cleanup(self.bot)


  @vc.command(name="setup", description="Setup voice creator")
  @guild_only()
  @commands.is_owner()
  async def setup(self, ctx: ApplicationContext, channel_name:str="Voice creator"):
    async with aiosqlite.connect("db/voice.db") as db:
      channel = await ctx.guild.create_voice_channel(channel_name, category=None)
      async with db.execute("SELECT channelID FROM GuildChannels WHERE guildID = ?", (ctx.guild.id,)) as cursor:
        old_channel_id = await cursor.fetchone()
        if old_channel_id is None:
          await db.execute ("INSERT INTO GuildChannels (guildID, channelID) VALUES (?, ?)",(ctx.guild.id, channel.id))
          await db.commit()
        else:
          old_channel = self.bot.get_channel(old_channel_id[0])
          if old_channel and isinstance(old_channel, VoiceChannel):
            await old_channel.delete(reason="Delete old voice creator")
          await db.execute ("UPDATE GuildChannels SET channelID = ? WHERE guildID = ?",(channel.id, ctx.guild.id))
          await db.commit()
        await ctx.respond(":gear:  **You are all setup and ready to go!**")


  @vc.command(name="claim", description="Claim active channel if owner is gone")
  @guild_only()
  @is_in_voice_channel()
  async def claim(self, ctx: ApplicationContext):
    channel = get_connected_voice_channel(ctx)
    if channel is None:
      await ctx.respond(":interrobang:  **You are not connected to any voice channel**")
    else:
      async with aiosqlite.connect("db/voice.db") as db:
        async with db.execute("SELECT ownerID FROM VoiceChannels WHERE channelID = ?", (channel.id,)) as cursor:
          owner_id = await cursor.fetchone()
          if owner_id:
            owner_id = owner_id[0]
            if owner_id == ctx.user.id:
              await ctx.respond(":crown:  **You already are owner of this channel**")
            elif any(member.id == owner_id for member in channel.members):
              await ctx.respond(":interrobang:  **Channel owner is still present**")
            else:
              await db.execute("UPDATE VoiceChannels SET ownerID = ? WHERE channelID = ?", (ctx.user.id, channel.id))
              await db.commit()
              await ctx.respond(":crown:  **You are now owner of the channel**")
          else:
            await ctx.respond(":interrobang:  **There is no ownership to be claimed in this channel**")


  @vc.command(name="lock", description="Lock active channel")
  @guild_only()
  @is_in_voice_channel()
  @is_voice_owner()
  async def lock(self, ctx: ApplicationContext):
    await ctx.user.voice.channel.edit(connect = False)
    await ctx.respond(":lock:  **Your channel has been locked**")


  @vc.command(name="unlock", description="Unlock active channel")
  @guild_only()
  @is_in_voice_channel()
  @is_voice_owner()
  async def unlock(self, ctx: ApplicationContext):
    await ctx.user.voice.channel.edit(connect = True)
    await ctx.respond(":unlock:  **Your channel has been unlocked**")


  @vc.command(name="limit", description="Limit active channel")
  @guild_only()
  @is_in_voice_channel()
  @is_voice_owner()
  async def limit(self, ctx: ApplicationContext, limit: int=0):
    await ctx.user.voice.channel.edit(user_limit = limit)
    await ctx.respond(f":tada:  **Channel user limit has been removed**" if limit == 0 else f":tickets:  **Channel user limit has been set to {limit}**")


  @vc.command(name="hide", description="Hide active channel")
  @guild_only()
  @is_in_voice_channel()
  @is_voice_owner()
  async def hide(self, ctx: ApplicationContext):
    await ctx.user.voice.channel.set_permissions(ctx.guild.default_role, view_channel=False)
    await ctx.respond(":dotted_line_face:  **Your channel is now invisible**")


  @vc.command(name="reveal", description="Reveal active channel")
  @guild_only()
  @is_in_voice_channel()
  @is_voice_owner()
  async def reveal(self, ctx: ApplicationContext):
    await ctx.user.voice.channel.set_permissions(ctx.guild.default_role, view_channel=True)
    await ctx.respond(":camera:  **Your channel is now visible**")


  @vc.command(name="rename", description="Rename active channel")
  @guild_only()
  @is_in_voice_channel()
  @is_voice_owner()
  async def rename(self, ctx: ApplicationContext, name:str):
    await ctx.user.voice.channel.edit(name = name)
    await ctx.respond(f":pen_ballpoint:  **Channel has been renamed to {name}**")


  settings = vc.create_subgroup("settings", description="Voice creator settings")


  @settings.command(name="set", description="Defaul channel settings")
  @guild_only()
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
  @guild_only()
  async def reset(self, ctx):
    async with aiosqlite.connect("db/voice.db") as db:
      async with db.execute("SELECT * FROM UserSettings WHERE userID = ?", (ctx.user.id,)) as cursor:
        if await cursor.fetchone():
          await db.execute ("DELETE FROM UserSettings WHERE userID = ?",(ctx.user.id,))
          await db.commit()
          await ctx.respond(":wastebasket:  **Default channel settings reset**")
        else:
          await ctx.respond(":interrobang:  **There were no settings to reset**")


  async def cog_command_error(self, ctx: ApplicationContext, error: CommandError):
    match error:
      case NotVoiceOwner():
        await ctx.respond(":interrobang:  **You are not owner of the channel**", ephemeral=True)
        return
      case NotInVoiceChannel():
        await ctx.respond(":interrobang:  **You are not connected to any voice channel**", ephemeral=True)
        return
      case NoPrivateMessage():
        await ctx.respond(":interrobang:  **This command shoul be used in a discord server**", ephemeral=True)
        return
      case _:
        raise error


def setup(bot):
  logger.info("[~~] Loading vc...")
  bot.add_cog(VCCog(bot))
  logger.info("[OK] vc loaded")
