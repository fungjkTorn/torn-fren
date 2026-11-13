"""Discord commands backed by the website's published and approved forecast feed."""
from typing import Literal
import asyncio
import discord

from bot import config, site_feed
from modules import stock

CountryCode = Literal[
    "mex", "cay", "can", "haw", "uni", "arg", "swi",
    "jap", "chi", "uae", "sou",
]


async def item_name_autocomplete(interaction: discord.Interaction, current: str):
    try:
        country = getattr(interaction.namespace, "country", None)
        if not country:
            return []
        names = await asyncio.to_thread(stock.get_known_item_names, country)
        matches = [name for name in names if current.casefold() in name.casefold()]
        return [discord.app_commands.Choice(name=name, value=name) for name in matches[:25]]
    except Exception:
        return []


def _site_view(country=None, item=None):
    url = site_feed.site_url(config.PUBLIC_BASE_URL, country=country, item=item)
    if not url:
        return None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="🌐 Open Torn-FREN", style=discord.ButtonStyle.link, url=url))
    return view


def _board():
    return site_feed.fetch_board(config.PUBLIC_BASE_URL)


def _safe_send_text(text):
    # Discord message bodies have a 2,000-character limit.
    if len(text) <= 1950:
        return text
    return text[:1880] + "\n…More items available on the Torn-FREN website."


def setup_commands(bot):
    @bot.tree.command(name="stock", description="Show the most recently observed foreign shop stock")
    async def stock_command(interaction: discord.Interaction, country: CountryCode):
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(stock.format_stock_message, country)
            await interaction.followup.send(_safe_send_text(result), view=_site_view())
        except Exception:
            await interaction.followup.send("⚠️ Could not read collected stock data.")

    @bot.tree.command(name="predict", description="Get the website's approved live-beta travel decision")
    @discord.app_commands.autocomplete(item_name=item_name_autocomplete)
    async def predict_command(interaction: discord.Interaction, country: CountryCode, item_name: str):
        await interaction.response.defer(thinking=True)
        try:
            board = await asyncio.to_thread(_board)
            row = site_feed.item_row(board, country, item_name)
            text = site_feed.format_prediction(country, item_name, row)
        except site_feed.FeedUnavailable:
            text = ("⚠️ The approved Torn-FREN forecast feed is unavailable. "
                    "No departure recommendation will be shown. Try the website for observed stock.")
        await interaction.followup.send(_safe_send_text(text), view=_site_view(country, item_name))

    @bot.tree.command(name="history", description="Show observed >30-stock history from the website")
    @discord.app_commands.autocomplete(item_name=item_name_autocomplete)
    async def history_command(interaction: discord.Interaction, country: CountryCode, item_name: str):
        await interaction.response.defer(thinking=True)
        try:
            summary = await asyncio.to_thread(
                site_feed.fetch_history_summary, config.PUBLIC_BASE_URL, country, item_name
            )
            try:
                board = await asyncio.to_thread(_board)
                row = site_feed.item_row(board, country, item_name)
            except site_feed.FeedUnavailable:
                row = None
            text = site_feed.format_history(country, item_name, summary, row)
        except site_feed.FeedUnavailable:
            text = ("⚠️ Website-backed history is unavailable. "
                    "No legacy prediction or accuracy percentage is being substituted.")
        await interaction.followup.send(_safe_send_text(text), view=_site_view(country, item_name))

    @bot.tree.command(name="site", description="Open the official Torn-FREN travel dashboard")
    async def site_command(interaction: discord.Interaction):
        url = site_feed.site_url(config.PUBLIC_BASE_URL)
        if not url:
            await interaction.response.send_message("⚠️ Torn-FREN website URL is not configured.")
            return
        await interaction.response.send_message("🌐 Open Torn-FREN to view travel decisions and live graphs.", view=_site_view())

    @bot.tree.command(name="alerts", description="Check whether observed stock notifications are active")
    async def alert_command(interaction: discord.Interaction):
        if not config.RESTOCK_ALERTS_ENABLED or not config.RESTOCK_ALERT_ITEMS:
            message = "🔕 Observed-stock alerts are currently disabled. Forecast departure alerts are not enabled."
        else:
            message = ("🔔 Observed-stock alerts are enabled for configured tracked items. "
                       "Alerts identify newly observed crossings above 30 units, not guaranteed physical restocks. "
                       "Forecast departure alerts are not enabled.")
        await interaction.response.send_message(message)

    @bot.tree.command(name="status", description="Check Discord and public prediction-feed status")
    async def status_command(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            board = await asyncio.to_thread(_board)
            rows = board.get("rows", [])
            ready = sum(site_feed.row_status(row) in site_feed.ALLOWED_DECISIONS for row in rows)
            stale = sum(site_feed.row_status(row) == "STALE_DATA" for row in rows)
            message = (
                f"🤖 Torn-FREN bot online • Version {config.VERSION}\n"
                f"🌐 Website feed: {board.get('status')}\n"
                f"📊 Published items: {len(rows)}; actionable: {ready}; stale: {stale}\n"
                f"🔔 Observed-stock alerts: {'enabled' if config.RESTOCK_ALERTS_ENABLED and config.RESTOCK_ALERT_ITEMS else 'disabled'}\n"
                "Predicted departure alerts: not enabled"
            )
        except site_feed.FeedUnavailable:
            message = "🤖 Discord bot online, but the website forecast feed is unavailable. Predictions are suppressed."
        await interaction.followup.send(message)

    @bot.tree.command(name="ping", description="Check if the Discord bot is responding")
    async def ping_command(interaction: discord.Interaction):
        await interaction.response.send_message("pong!")

    @bot.tree.command(name="help", description="List Torn-FREN commands")
    async def help_command(interaction: discord.Interaction):
        await interaction.response.send_message(
            "**📚 Torn-FREN Bot**\n"
            "`/stock` — observed stock by country (with freshness warning)\n"
            "`/predict` — approved website forecast (never legacy V2 fallback)\n"
            "`/history` — observed >30 stock windows, not prediction success rates\n"
            "`/site` — open the website\n"
            "`/alerts` — notification status\n"
            "`/status` — website feed and bot health\n"
            "`/ping` — bot responsiveness\n"
            "Items without published models show under review; restock/departure estimates are not guaranteed."
        )
