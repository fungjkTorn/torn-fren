async def send_alert(bot, channel_id: int, title: str, description: str):
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(f"🚨 **{title}**\n{description}")
    else:
        print(f"Could not send alert — channel {channel_id} not found.")