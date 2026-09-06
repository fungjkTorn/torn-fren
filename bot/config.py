import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))   # #torn-alerts channel ID
GUILD_ID = int(os.getenv("GUILD_ID"))       # Server ID

VERSION = "0.2"