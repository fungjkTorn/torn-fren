import discord
from discord.ext import commands
from bot import config
from bot.commands import setup_commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
ANNOUNCE_ON_STARTUP = False # set True only when you want the bot to post "online" to Discord

setup_commands(bot)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    guild = discord.Object(id=config.GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} slash command(s) to guild")

    channel = bot.get_channel(config.CHANNEL_ID)

    if (channel and ANNOUNCE_ON_STARTUP):
        await channel.send("Torn Fren bot is online!")
    else:
         print("Bot Ready")