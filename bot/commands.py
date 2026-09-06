import discord
from bot import config, alerts
from modules import travel

def setup_commands(bot):
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
            "**Torn Fren Bot Commands**\n\n"
            "/ping - Check if the bot is responsive\n"
            "/status - Show bot status\n"
            "/help - List available commands\n"
            "/testalert - Send a test alert\n"
            "/travel - Get travel info for a country"
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