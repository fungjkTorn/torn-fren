import asyncio
import logging
import time
from pathlib import Path

import discord
from discord.ext import commands
from bot import config
from bot.commands import setup_commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
ANNOUNCE_ON_STARTUP = False  # set True only when you want the bot to post "online" to Discord

setup_commands(bot)

LOG_PATH = Path(__file__).parent.parent / "data" / "connection_events.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
connection_logger = logging.getLogger("torn_fren.connection")
connection_logger.setLevel(logging.INFO)
if not connection_logger.handlers:
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    connection_logger.addHandler(handler)

last_disconnect_monotonic = None


async def _probe_host(host: str, port: int = 443, timeout: float = 3.0):
    """Small TCP reachability probe used only for gateway diagnostics."""
    started = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True, elapsed_ms, None
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


async def _log_network_snapshot(reason: str):
    discord_result, internet_result = await asyncio.gather(
        _probe_host("discord.com"),
        _probe_host("1.1.1.1"),
    )
    discord_ok, discord_ms, discord_error = discord_result
    internet_ok, internet_ms, internet_error = internet_result
    connection_logger.info(
        "%s | discord_tcp=%s latency_ms=%s error=%s | internet_tcp=%s latency_ms=%s error=%s | websocket_latency_ms=%s",
        reason,
        discord_ok,
        discord_ms,
        discord_error,
        internet_ok,
        internet_ms,
        internet_error,
        round(bot.latency * 1000, 1) if bot.latency == bot.latency else None,
    )


@bot.event
async def on_connect():
    connection_logger.info("Discord gateway CONNECTED")


@bot.event
async def on_disconnect():
    global last_disconnect_monotonic
    last_disconnect_monotonic = time.monotonic()
    connection_logger.warning("Discord gateway DISCONNECTED")
    asyncio.create_task(_log_network_snapshot("disconnect snapshot"))


@bot.event
async def on_resumed():
    global last_disconnect_monotonic
    downtime = None
    if last_disconnect_monotonic is not None:
        downtime = time.monotonic() - last_disconnect_monotonic
    connection_logger.info(
        "Discord gateway RESUMED | disconnect_duration_seconds=%s | websocket_latency_ms=%s",
        round(downtime, 2) if downtime is not None else None,
        round(bot.latency * 1000, 1) if bot.latency == bot.latency else None,
    )
    last_disconnect_monotonic = None
    asyncio.create_task(_log_network_snapshot("resume snapshot"))


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    connection_logger.info("Discord READY as %s", bot.user)

    guild = discord.Object(id=config.GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} slash command(s) to guild")

    channel = bot.get_channel(config.CHANNEL_ID)

    if channel and ANNOUNCE_ON_STARTUP:
        await channel.send("Torn Fren bot is online!")
    else:
        print("Bot Ready")
