import discord
from datetime import datetime

embed = discord.Embed(title="Example Title",
                      url="https://example.com",
                      description="This is an example description. Markdown works too!\n\nhttps://automatic.links\n> Block Quotes\n```\nCode Blocks\n```\n*Emphasis* or _emphasis_\n`Inline code` or ``inline code``\n[Links](https://example.com)\n<@123>, <@!123>, <#123>, <@&123>, @here, @everyone mentions\n||Spoilers||\n~~Strikethrough~~\n**Strong**\n__Underline__",
                      colour=0x00b0f4,
                      timestamp=datetime.now())

embed.set_author(name="Info",
                 url="https://example.com")

embed.add_field(name="Field Name",
                value="This is the field value.",
                inline=False)
embed.add_field(name="The first inline field.",
                value="This field is inline.",
                inline=True)
embed.add_field(name="The second inline field.",
                value="Inline fields are stacked next to each other.",
                inline=True)
embed.add_field(name="The third inline field.",
                value="You can have up to 3 inline fields in a row.",
                inline=True)
embed.add_field(name="Even if the next field is inline...",
                value="It won't stack with the previous inline fields.",
                inline=True)

embed.set_image(url="https://cubedhuang.com/images/alex-knight-unsplash.webp")

embed.set_thumbnail(url="https://dan.onl/images/emptysong.jpg")

embed.set_footer(text="Example Footer",
                 icon_url="https://slate.dan.onl/slate.png")
