import discord
from bot import config, alerts
from modules import travel
from typing import Literal
from modules import stock

CountryCode = Literal["mex", "cay", "can", "haw", "uni", "arg", "swi", "jap", "chi", "uae", "sou"]

async def item_name_autocomplete(interaction: discord.Interaction, current: str):
    country = getattr(interaction.namespace, "country", None)
    if not country:
        return []

    names = stock.get_item_names(country)
    matches = [name for name in names if current.lower() in name.lower()]

    return [
        discord.app_commands.Choice(name=name, value=name)
        for name in matches[:25]  # Discord caps autocomplete results at 25
    ]

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

    @bot.tree.command(name="ping", description="Check if the bot is responsive")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("pong!")

    @bot.tree.command(name="status", description="Show bot status")
    async def status(interaction: discord.Interaction):
        message = (
            "**Torn Fren is Online!**\n\n"
            f"*Version:* {config.VERSION}\n"
            "Watching: Nothing\n"
            "Alerts Enabled: 0"
        )
        await interaction.response.send_message(message)

@bot.tree.command(name="help", description="List available commands")
async def help_command(interaction: discord.Interaction):
    message = (
        "**📚 Torn Fren Commands**\n\n"
        "**General**\n"
        "• `/ping` - Check if the bot is online\n"
        "• `/status` - Show bot status\n"
        "• `/help` - Show this help menu\n\n"
        "**Travel Stock**\n"
        "• `/stock <country>` - Show the latest stock for a country\n"
        "• `/predict <country> <item>` - Estimate the next restock using historical data\n\n"
        "**Testing**\n"
    )

    await interaction.response.send_message(message)

    @bot.tree.command(name="testalert", description="Send a test alert to confirm the alert system works")
    async def testalert(interaction: discord.Interaction):
        await alerts.send_alert(bot, config.CHANNEL_ID, "Pickpocket Alert", "Walking Jogger detected!")
        await interaction.response.send_message("Test alert sent!", ephemeral=True)

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