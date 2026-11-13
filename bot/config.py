import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))   # #torn-alerts channel ID
GUILD_ID = int(os.getenv("GUILD_ID"))       # Server ID
TORN_API_KEY = os.getenv("TORN_API_KEY")  # Torn API key
VERSION = "0.4-dev"
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")

# Stock notifications are opt-in and never enabled merely by installing code.
RESTOCK_ALERTS_ENABLED = os.getenv("RESTOCK_ALERTS_ENABLED", "").strip().lower() in {"1", "true", "yes"}
RESTOCK_ALERT_ITEMS = tuple(
    item.strip() for item in os.getenv("RESTOCK_ALERT_ITEMS", "").split(";") if item.strip()
)
RESTOCK_ALERT_CHANNEL_ID = int(os.getenv("RESTOCK_ALERT_CHANNEL_ID") or CHANNEL_ID)
RESTOCK_ALERT_STATE = os.getenv("RESTOCK_ALERT_STATE", "data/discord_restock_alert_cursor.json")
