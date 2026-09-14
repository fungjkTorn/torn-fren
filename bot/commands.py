from typing import Literal

import discord

from bot import alerts, config
from modules import stock, travel

CountryCode = Literal[
    "mex",
    "cay",
    "can",
    "haw",
    "uni",
    "arg",
    "swi",
    "jap",
    "chi",
    "uae",
    "sou",
]


async def item_name_autocomplete(interaction: discord.Interaction, current: str):
    """
    Fast autocomplete for item names.

    Important:
    Do NOT call YATA here. Discord autocomplete must respond quickly.
    We only use locally stored database item names.
    """
    try:
        country = getattr(interaction.namespace, "country", None)

        if not country:
            return []

        names = stock.get_known_item_names(country)

        current_lower = current.lower()

        matches = [
            name for name in names
            if current_lower in name.lower()
        ]

        return [
            discord.app_commands.Choice(name=name, value=name)
            for name in matches[:25]
        ]

    except Exception as e:
        print(f"Autocomplete failed: {e}")
        return []

def setup_commands(bot):

    @bot.tree.command(name="stock", description="Show current abroad stock for a country")
    async def stock_command(interaction: discord.Interaction, country: CountryCode):
        message = stock.format_stock_message(country)
        await interaction.response.send_message(message)

    @bot.tree.command(name="predict", description="Predict the next restock time for an item")
    @discord.app_commands.autocomplete(item_name=item_name_autocomplete)
    async def predict_command(interaction: discord.Interaction, country: CountryCode, item_name: str):
        message = stock.format_restock_message(country, item_name)
        await interaction.response.send_message(message)

    @bot.tree.command(name="history", description="Show recent stock history for an item")
    @discord.app_commands.autocomplete(item_name=item_name_autocomplete)
    async def history_command(
        interaction: discord.Interaction,
        country: CountryCode,
        item_name: str,
        limit: int = 15,
    ):
        if limit < 1:
            limit = 1

        if limit > 25:
            limit = 25

        message = stock.format_history_message(country, item_name, limit=limit)
        await interaction.response.send_message(message)

    @bot.tree.command(name="ping", description="Check if the bot is responsive")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("pong!")

    @bot.tree.command(name="status", description="Show bot status")
    async def status(interaction: discord.Interaction):
        message = (
            "**Torn Fren is Online!**\n\n"
            f"*Version:* {config.VERSION}\n"
            "Watching: Travel stock\n"
            "Alerts Enabled: 0"
        )

        await interaction.response.send_message(message)

    @bot.tree.command(name="help", description="List available commands")
    async def help_command(interaction: discord.Interaction):
        message = (
            "**📚 Torn Fren Bot Commands**\n\n"
            "**General**\n"
            "• `/ping` - Check if the bot is responsive\n"
            "• `/status` - Show bot status\n"
            "• `/help` - List available commands\n\n"
            "**Travel Stock**\n"
            "• `/stock <country>` - Show current abroad stock for a country\n"
            "• `/predict <country> <item_name>` - Estimate the next restock time\n"
            "• `/history <country> <item_name>` - Show recent recorded stock changes\n\n"
        )

        await interaction.response.send_message(message)

    @bot.tree.command(name="travel", description="Get travel info for a country")
    async def travel_command(interaction: discord.Interaction, country: str):
        info = travel.get_travel_info(country)

        if not info:
            await interaction.response.send_message(f"No data for '{country}' yet.")
            return

        items = "\n".join(f"• {item}" for item in info["items"])

        message = (
            f"{info['flag']} **{info['name']}**\n\n"
            f"**Travel Time**\n{info['travel_time']}\n\n"
            f"**Items**\n{items}\n\n"
            f"**Status**\nComing Soon..."
        )

        await interaction.response.send_message(message)