from __future__ import annotations

import discord

from services.arbitrage_live import build_arbitrage_report


def _money(value) -> str:
    return f"${int(round(float(value or 0))):,}"


def _pct(value) -> str:
    return f"{float(value or 0) * 100:.1f}%"


def _safe_link(label: str, url: str | None) -> str:
    if not url:
        return label
    return f"[{label}]({url.replace(')', '%29')})"


def build_arbitrage_embed(
    *,
    min_profit_per_item: int = 20_000,
    min_roi: float = 0.0,
    min_quantity: int = 1,
    limit: int = 8,
) -> discord.Embed:
    report = build_arbitrage_report(
        min_profit_per_item=min_profit_per_item,
        min_roi=min_roi,
        min_quantity=min_quantity,
        background=True,
    )
    rows = (report.get("opportunities") or [])[: max(1, min(limit, 10))]

    embed = discord.Embed(
        title="💸 Foreign Item Arbitrage",
        description=(
            f"Foreign-purchasable items only · minimum **{_money(min_profit_per_item)} profit/item**"
            f" · minimum **{_pct(min_roi)} ROI**"
        ),
        color=0x43D17B,
    )

    if not rows:
        if report.get("refreshing"):
            embed.add_field(
                name="Scanner warming up",
                value=(
                    "A source refresh is running in the background. "
                    "Run `/arbitrage` again shortly or open the web scanner."
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="No qualifying opportunities",
                value="No currently ingested bazaar/trader pair clears these filters.",
                inline=False,
            )
    else:
        for index, row in enumerate(rows, start=1):
            trader = _safe_link(
                str(row.get("buyer_name") or "Trader"),
                row.get("buyer_url"),
            )
            buy = _safe_link("Buy listings", row.get("buy_url"))
            countries = ", ".join(row.get("countries") or []) or "Foreign"
            embed.add_field(
                name=f"{index}. {row.get('item_name')}",
                value=(
                    f"Avg cost **{_money(row.get('average_buy_price'))}** × "
                    f"**{int(row.get('quantity') or 0):,}**
"
                    f"Sell **{_money(row.get('buyer_price'))}** → {trader}
"
                    f"Profit/item **{_money(row.get('average_profit_per_item'))}** · "
                    f"Total **{_money(row.get('total_profit'))}** · "
                    f"ROI **{_pct(row.get('roi'))}**
"
                    f"{buy} · {countries} · {int(row.get('seller_count') or 0)} sellers"
                ),
                inline=False,
            )

    error_count = len(report.get("errors") or [])
    refresh_note = " · refreshing" if report.get("refreshing") else ""
    embed.set_footer(
        text=(
            f"{report.get('catalog_count', 0)} foreign items · "
            f"{report.get('listing_count', 0)} buy listings · "
            f"{report.get('offer_count', 0)} trader offers · "
            f"{error_count} source errors{refresh_note}"
        )
    )
    return embed
