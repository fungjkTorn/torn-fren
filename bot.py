import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
test = True
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) # #torn-alerts channel ID
GUILD_ID = int(os.getenv("GUILD_ID"))   # Server ID

VERSION = "0.1"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!",intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)

    print(f"Synced {len(synced)} slash command(s) to guild")

    channel = bot.get_channel(CHANNEL_ID)
    if (channel and test):
            await channel.send("Torn Fren bot is online!")
    else:
         print("Bot Ready")

async def send_alert(title: str, description: str):
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(f"🚨 **{title}**\n{description}")
    else:
        print("Channel not found")

@bot.tree.command(name="testalert", description = "Send a test alert to the channel to confirm alarm system works")
async def test_alert(interaction: discord.Interaction):
    await send_alert("Pickpocket Alert", "Walking Jogger detected!")
    await interaction.response.send_message("Test alert sent!", ephemeral=True)

@bot.tree.command(name="ping", description = "Check if the bot is responsive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong!")
    
@bot.tree.command(name="status", description = "Show bot status")
async def status(interaction: discord.Interaction):
     message = (
          "**Torn Fren is Online!**\n\n"
          f"*Version:* {VERSION}\n"
          "Watching: Nothing\n"
          "Alerts Enabled: 0"
    )
     await interaction.response.send_message(message)

@bot.tree.command(name="help", description = "List available commands")
async def help_command(interaction: discord.Interaction):
     message = (
          "**Torn Fren Bot Commands**\n\n"
          "/ping - Check if the bot is responsive\n"
          "/status - Show bot status\n"
          "/help - List available commands"
    )
     await interaction.response.send_message(message)



bot.run(TOKEN)



