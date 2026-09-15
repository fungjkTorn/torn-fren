import time

from services.history_service import (
    get_item_history,
    get_known_items,
    get_latest_stock_snapshot,
    get_restock_prediction,
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


def _format_age(timestamp):
    if timestamp is None:
        return "unknown"

    seconds = max(0, int(time.time()) - timestamp)

    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    return f"{hours}h {remaining_minutes}m"


def _format_timestamp(timestamp):
    if timestamp is None:
        return "Unknown"

    return time.strftime(
        "%I:%M:%S %p",
        time.localtime(timestamp),
    )


def format_stock_message(country_code: str) -> str:
    """
    Show the latest stock state stored in SQLite.

    This intentionally does NOT call YATA or Prometheus.
    The poller is responsible for collecting live data.

    This means /stock can still work if the external APIs
    are temporarily unavailable.
    """
    stock = get_latest_stock_snapshot(country_code)

    label = COUNTRY_NAMES.get(
        country_code,
        country_code.upper(),
    )

    if not stock:
        return (
            f"No stock data found for {label} yet.\n"
            "The poller may not have collected data for this country."
        )

    # Highest stock first.
    stock = sorted(
        stock,
        key=lambda item: item["quantity"],
        reverse=True,
    )

    latest_timestamp = max(
        item["timestamp"]
        for item in stock
    )

    latest_source = next(
        (
            item["source"]
            for item in stock
            if item["timestamp"] == latest_timestamp
        ),
        "unknown",
    )

    age_str = _format_age(latest_timestamp)

    lines = [
        f"**{label} — Current Stock**",
        f"_Latest recorded data: {age_str} ago via {latest_source}_",
        "",
    ]

    for item in stock:
        quantity = item["quantity"]
        cost = item["cost"]

        cost_text = (
            f"${cost:,}"
            if cost is not None
            else "Unknown"
        )

        lines.append(
            f"• **{item['name']}** — "
            f"Stock: **{quantity:,}** | "
            f"Cost: **{cost_text}**"
        )

    return "\n".join(lines)


def get_known_item_names(country_code: str):
    """
    Return item names from the local SQLite database.

    Autocomplete must stay fast, so this function never
    makes an external API request.
    """
    return get_known_items(country_code)


def format_restock_message(
    country_code: str,
    item_name: str,
) -> str:

    label = COUNTRY_NAMES.get(
        country_code,
        country_code.upper(),
    )

    result = get_restock_prediction(
        country_code,
        item_name,
    )

    if result is None:
        return (
            f"No history found for **{item_name}** "
            f"in {label} yet.\n"
            "Keep collecting snapshots."
        )

    lines = [
        f"**{item_name} — {label}**",
        "",
        f"Current Stock: **{result['current_stock']:,}**",
        f"Last Recorded Change: **{result['latest_time_str']}**",
        f"Observed Restocks: **{result['observed_restocks']}**",
        f"Average Sellout Time: **{result['avg_sellout_str']}**",
        f"Sellout Samples: **{result['sellout_samples']}**",
    ]

    if result["avg_interval_minutes"] is None:
        lines.extend([
            "",
            "Prediction: **Not enough restocks observed yet.**",
        ])

    else:
        lines.extend([
            "",
            (
                "Average Restock Interval: "
                f"**{result['avg_interval_minutes']:.1f} minutes**"
            ),
            (
                "Next Estimated Restock: "
                f"**{result['predicted_next_str']}**"
            ),
        ])

        second_next = result.get(
            "predicted_second_next_str"
        )

        if second_next:
            lines.append(
                "Second Estimated Restock: "
                f"**{second_next}**"
            )

    return "\n".join(lines)


def format_history_message(
    country_code: str,
    item_name: str,
    limit: int = 15,
) -> str:

    label = COUNTRY_NAMES.get(
        country_code,
        country_code.upper(),
    )

    result = get_restock_prediction(
        country_code,
        item_name,
    )

    history = get_item_history(
        country_code,
        item_name,
        limit=limit,
    )

    if not history:
        return (
            f"No history found for **{item_name}** "
            f"in {label} yet."
        )

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
            lines.extend([
                (
                    "Average Restock Interval: "
                    f"**{result['avg_interval_minutes']:.1f} minutes**"
                ),
                (
                    "Predicted Next Restock: "
                    f"**{result['predicted_next_str']}**"
                ),
                "",
            ])

    lines.append(
        f"**Last {len(history)} Recorded Changes**"
    )

    for row in history:
        timestamp = _format_timestamp(
            row["timestamp"]
        )

        quantity = row["quantity"]
        cost = row["cost"]

        cost_text = (
            f"${cost:,}"
            if cost is not None
            else "Unknown"
        )

        lines.append(
            f"• {timestamp} → "
            f"**{quantity:,}** stock at "
            f"**{cost_text}**"
        )

    return "\n".join(lines)