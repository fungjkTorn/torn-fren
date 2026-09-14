from services.yata_api import get_country_stock
from services.history_service import get_restock_prediction, get_known_items

COUNTRY_NAMES = {
    "mex": "🇲🇽 Mexico",
    "cay": "🏝️ Cayman Islands",
    "can": "🇨🇦 Canada",
    "haw": "🌺 Hawaii",
    "uni": "🇬🇧 United Kingdom",
    "arg": "🇦🇷 Argentina",
    "swi": "🇨🇭 Switzerland",
    "jap": "🇯🇵 Japan",
    "chi": "🇨🇳 China",
    "uae": "🇦🇪 UAE",
    "sou": "🇿🇦 South Africa",
}


def format_stock_message(country_code: str) -> str:
    stock = get_country_stock(country_code)
    label = COUNTRY_NAMES.get(country_code, country_code.upper())

    if not stock:
        return f"No stock data found for {label}."

    lines = [f"**{label} — Current Stock**\n"]
    for item in stock:
        lines.append(f"• {item['name']}: {item['quantity']} (${item['cost']:,})")

    return "\n".join(lines)

def get_item_names(country_code: str):
    """Combines live current stock (covers brand-new items) with everything ever
    recorded historically (covers items currently sold out at quantity 0)."""
    live_names = {item["name"] for item in get_country_stock(country_code)}
    known_names = set(get_known_items(country_code))
    return sorted(live_names | known_names)

def format_restock_message(country_code: str, item_name: str) -> str:
    label = COUNTRY_NAMES.get(country_code, country_code.upper())
    result = get_restock_prediction(country_code, item_name)

    if result is None:
        return f"No history found for **{item_name}** in {label} yet. Keep collecting snapshots."

    lines = [f"**{item_name} — {label}**\n"]
    lines.append(f"Current Stock: {result['current_stock']}")
    lines.append(f"Observed Restocks: {result['observed_restocks']}")

    if result["avg_interval_minutes"] is None:
        lines.append("Not enough restocks observed yet to estimate an average interval.")
    else:
        lines.append(f"Average Interval: {result['avg_interval_minutes']:.1f} minutes")
        lines.append(f"Predicted Next Restock: {result['predicted_next_str']}")

    return "\n".join(lines)