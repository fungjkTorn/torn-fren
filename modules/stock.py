import time
from services.history_service import get_known_items
from services.yata_api import get_country_stock, get_country_update_time
from services.history_service import (
    get_restock_prediction,
    get_known_items,
    get_item_history,
)

COUNTRY_NAMES = {
    "mex": "🇲🇽 Mexico",
    "cay": "🏝️ Cayman Islands",
    "can": "🍁 Canada",
    "haw": "🌺 Hawaii",
    "uni": "🇬🇧 United Kingdom",
    "arg": "🇦🇷 Argentina",
    "swi": "🇨🇭 Switzerland",
    "jap": "🇯🇵 Japan",
    "chi": "🇨🇳 China",
    "uae": "🇦🇪 UAE",
    "sou": "🇿🇦 South Africa",
}

def get_known_item_names(country_code: str):
    """
    Return item names from the local database only.

    This is used for Discord autocomplete because autocomplete needs to be fast.
    Do not call YATA from here.
    """
    return get_known_items(country_code)

def _format_timestamp(timestamp):
    if timestamp is None:
        return "Unknown"

    return time.strftime("%I:%M:%S %p", time.localtime(timestamp))


def format_stock_message(country_code: str) -> str:
    stock = get_country_stock(country_code)
    label = COUNTRY_NAMES.get(country_code, country_code.upper())

    if not stock:
        return f"No stock data found for {label}."

    # Sort by current stock amount, highest first.
    # Sold out / low stock items naturally fall to the bottom.
    stock = sorted(stock, key=lambda item: item["quantity"], reverse=True)

    lines = [f"**{label} — Current Stock**\n"]

    for item in stock:
        quantity = item["quantity"]
        cost = item["cost"]

        if quantity == 0:
            lines.append(f"• **{item['name']}** — Stock: **0** | Cost: **${cost:,}**")
        else:
            lines.append(f"• **{item['name']}** — Stock: **{quantity:,}** | Cost: **${cost:,}**")

    return "\n".join(lines)


def get_item_names(country_code: str):
    """
    Combines live current stock with everything ever recorded historically.
    This lets sold-out items still show up in autocomplete.
    """
    live_names = {item["name"] for item in get_country_stock(country_code)}
    known_names = set(get_known_items(country_code))
    return sorted(live_names | known_names)


def format_restock_message(country_code: str, item_name: str) -> str:
    label = COUNTRY_NAMES.get(country_code, country_code.upper())
    result = get_restock_prediction(country_code, item_name)

    if result is None:
        return f"No history found for **{item_name}** in {label} yet. Keep collecting snapshots."

    lines = [f"**{item_name} — {label}**", ""]

    lines.append(f"Current Stock: **{result['current_stock']:,}**")
    lines.append(f"Last Recorded Change: **{result['latest_time_str']}**")
    lines.append(f"Observed Restocks: **{result['observed_restocks']}**")
    lines.append(f"Average Sellout Time: **{result['avg_sellout_str']}**")
    lines.append(f"Sellout Samples: **{result['sellout_samples']}**")

    if result["avg_interval_minutes"] is None:
        lines.append("")
        lines.append("Prediction: **Not enough restocks observed yet.**")
    else:
        lines.append("")
        lines.append(f"Average Restock Interval: **{result['avg_interval_minutes']:.1f} minutes**")
        lines.append(f"Next Estimated Restock: **{result['predicted_next_str']}**")

        second_next = result.get("predicted_second_next_str")
        if second_next:
            lines.append(f"Second Estimated Restock: **{second_next}**")

    return "\n".join(lines)

def format_history_message(country_code: str, item_name: str, limit: int = 15) -> str:
    label = COUNTRY_NAMES.get(country_code, country_code.upper())
    result = get_restock_prediction(country_code, item_name)
    history = get_item_history(country_code, item_name, limit=limit)

    if not history:
        return f"No history found for **{item_name}** in {label} yet."

    lines = [
        f"**{item_name} — {label} History**",
        "",
    ]

    if result:
        lines.extend([
            f"Current Stock: **{result['current_stock']:,}**",
            f"Last Recorded Change: **{result['latest_time_str']}**",
            f"Observed Restocks: **{result['observed_restocks']}**",
            f"Average Sellout Time: **{result['avg_sellout_str']}**",
            "",
        ])

        if result["avg_interval_minutes"] is not None:
            lines.append(f"Average Restock Interval: **{result['avg_interval_minutes']:.1f} minutes**")
            lines.append(f"Predicted Next Restock: **{result['predicted_next_str']}**")
            lines.append("")

    lines.append(f"**Last {len(history)} Recorded Changes**")

    for row in history:
        timestamp = _format_timestamp(row["timestamp"])
        quantity = row["quantity"]
        cost = row["cost"]

        lines.append(f"• {timestamp} → **{quantity:,}** stock at **${cost:,}**")

    return "\n".join(lines)