from typing import Literal

import asyncio
from urllib.parse import urlencode

import discord

from bot import alerts, config
from modules import stock, travel
from modules.prediction_v2_discord import build_prediction_v2_embed
from modules.arbitrage_discord import build_arbitrage_embed
from services.history_service import get_recent_completed_cycles
from services.prediction_v2_live import build_live_prediction_v2
from services.arbitrage_live import build_arbitrage_report

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


def _history_duration(seconds):
    if seconds is None:
        return "—"
    seconds = max(0, int(round(float(seconds))))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _history_clock(timestamp):
    if timestamp is None:
        return "—"
    return f"<t:{int(timestamp)}:t>"


def _history_pct(value):
    if value is None:
        return "—"
    value = float(value)
    # Prediction v2 success rates are stored as fractions (0.979 = 97.9%).
    if 0.0 <= value <= 1.0:
        value *= 100.0
    return f"{value:.1f}%"



def _graph_url(country: str, item_name: str):
    base = (getattr(config, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    if not base:
        return None
    return f"{base}/?{urlencode({'country': country.lower(), 'item': item_name})}"


def _graph_view(country: str, item_name: str, label: str = "📈 Open Graph"):
    url = _graph_url(country, item_name)
    if not url:
        return None

    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.link,
            url=url,
        )
    )
    return view



def _arbitrage_url():
    base = (getattr(config, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    if not base:
        return None
    return f"{base}/arbitrage"


def _arbitrage_view():
    url = _arbitrage_url()
    if not url:
        return None
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="Open Arbitrage Scanner",
            style=discord.ButtonStyle.link,
            url=url,
        )
    )
    return view

def setup_commands(bot):

    @bot.tree.command(name="stock", description="Show current abroad stock for a country")
    async def stock_command(interaction: discord.Interaction, country: CountryCode):
        message = stock.format_stock_message(country)
        await interaction.response.send_message(message)

    @bot.tree.command(
        name="predict",
        description="Prediction v2: restock, leave-by, arrival, and travel reliability",
    )
    @discord.app_commands.autocomplete(item_name=item_name_autocomplete)
    async def predict_command(
        interaction: discord.Interaction,
        country: CountryCode,
        item_name: str,
    ):
        # A first-time model profile can take several seconds. Defer immediately
        # so Discord does not time the slash command out, and keep CPU-heavy
        # walk-forward work off the asyncio gateway loop.
        await interaction.response.defer(thinking=True)

        try:
            embed = await asyncio.to_thread(
                build_prediction_v2_embed,
                country,
                item_name,
            )
            view = _graph_view(country, item_name, "📈 Open Graph")
            await interaction.followup.send(embed=embed, view=view)
        except Exception as exc:
            print(f"/predict failed for {country}/{item_name}: {exc}")
            await interaction.followup.send(
                "⚠️ Prediction v2 could not be calculated right now. "
                "The stock collector can continue running; try `/predict` again shortly."
            )

    @bot.tree.command(name="history", description="Show the 3 most recent completed stock cycles")
    @discord.app_commands.autocomplete(item_name=item_name_autocomplete)
    async def history_command(
        interaction: discord.Interaction,
        country: CountryCode,
        item_name: str,
    ):
        await interaction.response.defer(thinking=True)

        try:
            cycle_data, prediction = await asyncio.gather(
                asyncio.to_thread(
                    get_recent_completed_cycles,
                    country,
                    item_name,
                    3,
                ),
                asyncio.to_thread(
                    build_live_prediction_v2,
                    country,
                    item_name,
                    None,
                    False,
                    "discord-history",
                    True,
                ),
            )
        except Exception as exc:
            print(f"/history failed for {country}/{item_name}: {exc}")
            await interaction.followup.send(
                "⚠️ Recent cycle history could not be calculated right now."
            )
            return

        cycles = cycle_data.get("cycles") or []
        typical = cycle_data.get("typical") or {}

        country_names = {
            "mex": "Mexico",
            "cay": "Cayman Islands",
            "can": "Canada",
            "haw": "Hawaii",
            "uni": "United Kingdom",
            "arg": "Argentina",
            "swi": "Switzerland",
            "jap": "Japan",
            "chi": "China",
            "uae": "UAE",
            "sou": "South Africa",
        }

        embed = discord.Embed(
            title=f"📚 {item_name} — {country_names.get(country, country.upper())}",
            description="Recent completed stock cycles",
            color=0x5865F2,
        )

        if not cycles:
            embed.add_field(
                name="Recent cycles",
                value="Not enough clean completed cycles are available yet.",
                inline=False,
            )
        else:
            number_emoji = ["1️⃣", "2️⃣", "3️⃣"]
            for index, cycle in enumerate(cycles):
                peak = cycle.get("peak_quantity")
                peak_text = f"{int(peak):,}" if peak is not None else "—"

                embed.add_field(
                    name=f"{number_emoji[index]} Cycle {index + 1}",
                    value=(
                        f"**Empty:** {_history_duration(cycle.get('zero_wait_seconds'))}"
                        f" · **Stock:** {_history_duration(cycle.get('stock_lifetime_seconds'))}"
                        f" · **Peak:** {peak_text}\n"
                        f"Depleted {_history_clock(cycle.get('depletion_time'))}"
                        f" → Restocked {_history_clock(cycle.get('next_restock_time'))}"
                    ),
                    inline=False,
                )

        embed.add_field(
            name="📊 Typical",
            value=(
                f"Empty → restock: **{_history_duration(typical.get('median_zero_wait_seconds'))}**\n"
                f"Stock lifetime: **{_history_duration(typical.get('median_stock_lifetime_seconds'))}**\n"
                f"Qualified cycles: **{int(typical.get('valid_cycle_count') or 0):,}**"
            ),
            inline=True,
        )

        active = prediction.get("display_prediction") or {}
        reliability = (
            active.get("travel_reliability")
            or prediction.get("travel_reliability")
            or "insufficient"
        ).upper()

        embed.add_field(
            name="🎯 Prediction",
            value=(
                f"Historical trip success: **{_history_pct(prediction.get('arrival_success_rate'))}**\n"
                f"Recent 10: **{_history_pct(prediction.get('recent10_arrival_success_rate'))}**\n"
                f"Travel reliability: **{reliability}**\n"
                f"Model evidence: **{(prediction.get('model_evidence_tier') or '—').upper()}**"
            ),
            inline=True,
        )

        embed.set_footer(
            text="Use /predict for the next trip decision · use the graph button for deeper history"
        )
        view = _graph_view(country, item_name, "📈 Open Full History")
        await interaction.followup.send(embed=embed, view=view)


    @bot.tree.command(
        name="arbitrage",
        description="Show top foreign-item bazaar → trader arbitrage opportunities",
    )
    async def arbitrage_command(
        interaction: discord.Interaction,
        min_profit: int = 20_000,
        min_quantity: int = 1,
    ):
        await interaction.response.defer(thinking=True)

        try:
            report = await asyncio.to_thread(
                build_arbitrage_report,
                min_profit_per_item=max(0, min_profit),
                min_quantity=max(1, min_quantity),
            )
        except Exception as exc:
            print(f"/arbitrage failed: {exc}")
            await interaction.followup.send(
                "⚠️ Arbitrage scan could not be completed right now."
            )
            return

        rows = report.get("opportunities") or []
        embed = discord.Embed(
            title="💱 Foreign Item Arbitrage",
            description=(
                f"Top bazaar → trader opportunities with at least "
                f"$" + f"{max(0, min_profit):,}" + " profit/item."
            ),
            color=0x48D597,
        )

        if not rows:
            embed.add_field(
                name="No qualifying opportunities",
                value="Nothing in the current foreign-item snapshot clears the filter.",
                inline=False,
            )
        else:
            for index, row in enumerate(rows[:6], start=1):
                trader = row.get("buyer_name") or "Unknown trader"
                trader_url = row.get("buyer_url")
                trader_text = f"[{trader}]({trader_url})" if trader_url else trader

                buy_url = row.get("buy_url")
                buy_text = f"[buy listings]({buy_url})" if buy_url else "buy listings unavailable"

                embed.add_field(
                    name=f"{index}. {row.get('item_name', 'Unknown item')}",
                    value=(
                        f"Avg cost $" + f"{row.get('average_buy_price', 0):,.0f}" + " → "
                        f"sell $" + f"{row.get('buyer_price', 0):,}" + "\n"
                        f"Qty **{row.get('quantity', 0):,}** · "
                        f"profit/item $" + f"{row.get('average_profit_per_item', 0):,.0f}" + " · "
                        f"total $" + f"{row.get('total_profit', 0):,.0f}" + "\n"
                        f"ROI **{row.get('roi', 0) * 100:.1f}%** · "
                        f"{row.get('listing_count', 0)} qualifying listing(s) · "
                        f"{buy_text} · sell to {trader_text}"
                    ),
                    inline=False,
                )

        error_count = len(report.get("errors") or [])
        embed.set_footer(
            text=(
                f"Foreign items only · {report.get('listing_count', 0)} bazaar listings · "
                f"{report.get('offer_count', 0)} trader bids · {error_count} source errors"
            )
        )

        await interaction.followup.send(embed=embed, view=_arbitrage_view())

    @bot.tree.command(
        name="arbitrage",
        description="Show current foreign-item arbitrage opportunities",
    )
    async def arbitrage_command(
        interaction: discord.Interaction,
        min_profit: int = 20_000,
        min_roi_percent: float = 0.0,
        min_quantity: int = 1,
    ):
        await interaction.response.defer(thinking=True)

        try:
            embed = await asyncio.to_thread(
                build_arbitrage_embed,
                min_profit_per_item=max(0, min_profit),
                min_roi=max(0.0, min_roi_percent) / 100.0,
                min_quantity=max(1, min_quantity),
                limit=8,
            )

            view = None
            base = (getattr(config, "PUBLIC_BASE_URL", "") or "").rstrip("/")
            if base:
                view = discord.ui.View()
                view.add_item(
                    discord.ui.Button(
                        label="Open Arbitrage Scanner",
                        style=discord.ButtonStyle.link,
                        url=f"{base}/arbitrage",
                    )
                )

            await interaction.followup.send(embed=embed, view=view)
        except Exception as exc:
            print(f"/arbitrage failed: {exc}")
            await interaction.followup.send(
                "⚠️ Arbitrage scan could not be calculated right now. "
                "Try again shortly or open the web scanner for source diagnostics."
            )

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
            "• `/predict <country> <item_name>` - Prediction v2 + direct graph link\n"
            "• `/history <country> <item_name>` - Show 3 recent cycles + full graph link\n\n"
            "**Arbitrage**\n"
            "• `/arbitrage` - Foreign-item bazaar/market → trader opportunities\n\n"
            "**Arbitrage**\n"
            "• `/arbitrage [min_profit] [min_quantity]` - Top foreign-item bazaar → trader spreads\n\n"
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