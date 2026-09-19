import time

import discord

from services.prediction_v2_live import build_live_prediction_v2


COUNTRY_NAMES = {
    "mex": ("🇲🇽", "Mexico"),
    "cay": ("🏝️", "Cayman Islands"),
    "can": ("🍁", "Canada"),
    "haw": ("🌺", "Hawaii"),
    "uni": ("🇬🇧", "United Kingdom"),
    "arg": ("🇦🇷", "Argentina"),
    "swi": ("🇨🇭", "Switzerland"),
    "jap": ("🇯🇵", "Japan"),
    "chi": ("🇨🇳", "China"),
    "uae": ("🇦🇪", "UAE"),
    "sou": ("🇿🇦", "South Africa"),
}

RELIABILITY_STYLE = {
    "excellent": ("🟢", 0x3BA55D),
    "good": ("🔵", 0x5865F2),
    "marginal": ("🟠", 0xFAA61A),
    "unreliable": ("🔴", 0xED4245),
    "insufficient": ("⚪", 0x71767D),
}


def _discord_time(timestamp, style="t"):
    if not timestamp:
        return "—"
    return f"<t:{int(timestamp)}:{style}>"


def _pct(value):
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _duration(seconds):
    if seconds is None:
        return "—"
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _target_line(prediction):
    if not prediction:
        return "⚫ **No reachable active target**"
    num = prediction.get("prediction_number") or 1
    if prediction.get("projected"):
        if num > 1:
            return f"🟠 **Prediction #{num} · NEXT REACHABLE CYCLE · PROJECTED**"
        return f"🟠 **Prediction #{num} · PROJECTED**"
    return f"🟢 **Prediction #{num} · observed depletion anchor**"


def _prediction_reference(prediction, label):
    if not prediction:
        return f"**{label}:** —"
    suffix = " · projected" if prediction.get("projected") else ""
    usable = "✅ reachable" if prediction.get("usable_for_departure") else "❌ not reachable"
    return (
        f"**{label}:** {_discord_time(prediction.get('estimate_timestamp'), 't')}"
        f"{suffix} · {usable}"
    )



def _prediction_chain_lines(result, active_number=None):
    predictions = result.get("predictions") or []
    if not predictions:
        predictions = [
            p for p in (result.get("prediction_1"), result.get("prediction_2"))
            if p
        ]

    lines = []
    for p in predictions:
        num = p.get("prediction_number") or 1
        marker = "👉" if active_number == num else ("✅" if p.get("usable_for_departure") else "❌")
        projected = " projected" if p.get("projected") else ""
        lines.append(
            f"{marker} **P{num}:** {_discord_time(p.get('estimate_timestamp'), 't')} · "
            f"{'reachable' if p.get('usable_for_departure') else 'not reachable'}{projected}"
        )
    return lines



def _leave_urgency(leave_by):
    """
    Visual urgency cue for the most important user action.
    Discord does not support arbitrary per-word text colors in embeds, so use
    strongly colored emoji + bold formatting while keeping the embed side color
    reserved for prediction reliability.
    """
    if not leave_by:
        return "⚪", "NO LEAVE TIME"

    remaining = float(leave_by) - time.time()

    if remaining <= 0:
        return "🔴", "LEAVE NOW / LATE"
    if remaining <= 10 * 60:
        return "🔴", "LEAVE VERY SOON"
    if remaining <= 30 * 60:
        return "🟠", "LEAVE SOON"
    return "🟢", "LEAVE BY"


def build_prediction_v2_embed(country_code: str, item_name: str) -> discord.Embed:
    result = build_live_prediction_v2(country_code, item_name)
    country_code = country_code.lower()
    flag, country_name = COUNTRY_NAMES.get(
        country_code, ("🌍", country_code.upper())
    )

    active = result.get("display_prediction")
    reliability = (
        (active or {}).get("travel_reliability")
        or result.get("travel_reliability")
        or "insufficient"
    ).lower()
    reliability_emoji, color = RELIABILITY_STYLE.get(
        reliability, RELIABILITY_STYLE["insufficient"]
    )

    embed = discord.Embed(
        title=f"{flag} {item_name} — {country_name}",
        color=color,
    )

    stock = result.get("current_stock")
    stock_text = f"{stock:,}" if isinstance(stock, int) else "—"

    if active:
        active_num = active.get("prediction_number") or 1
        projected = bool(active.get("projected"))
        embed.description = (
            f"{_target_line(active)}\n"
            f"📦 Current stock: **{stock_text}**\n"
            f"{reliability_emoji} Travel reliability: **{reliability.upper()}**"
        )

        window_start = active.get("window_start_timestamp")
        window_end = active.get("window_end_timestamp")
        window_text = (
            f"{_discord_time(window_start, 't')} – {_discord_time(window_end, 't')}"
            if window_start and window_end else "Not enough calibrated history"
        )

        leave_by = active.get("recommended_leave_by_timestamp")
        arrival = active.get("recommended_arrival_timestamp")
        travel = active.get("travel_seconds")
        fallback = active.get("arrival_offset_source") == "mid-stock fallback"
        suffix = " *(best-effort)*" if fallback else ""

        # Departure time is the primary action. Discord embeds cannot color
        # individual words reliably, so use a colored urgency marker + strong
        # formatting while keeping the embed side color tied to reliability.
        urgency_emoji, urgency_text = _leave_urgency(leave_by)
        embed.add_field(
            name=f"{urgency_emoji}⏰✈️  {urgency_text}",
            value=(
                f"**━━━━━━━━━━━━━━━━━━**\n"
                f"**{urgency_emoji}  {_discord_time(leave_by, 't')}  •  {_discord_time(leave_by, 'R')}**{suffix}\n"
                f"**━━━━━━━━━━━━━━━━━━**\n"
                f"🎯 Target arrival: {_discord_time(arrival, 't')}{suffix}\n"
                f"🛫 Flight: {_duration(travel)}"
            ),
            inline=False,
        )

        embed.add_field(
            name="🎯 Estimated restock",
            value=(
                f"**{_discord_time(active.get('estimate_timestamp'), 'F')}**\n"
                f"Window: {window_text}"
            ),
            inline=False,
        )


        embed.add_field(
            name="📊 Historical performance",
            value=(
                f"All resolved trips: **{_pct(result.get('arrival_success_rate'))}**\n"
                f"Recent 10 trips: **{_pct(result.get('recent10_arrival_success_rate'))}**"
            ),
            inline=True,
        )

        if projected:
            cycles_before = max(0, active_num - 1)
            embed.add_field(
                name="⚠️ Projection notice",
                value=(
                    f"Prediction #{active_num} is {cycles_before} cycle"
                    f"{'' if cycles_before == 1 else 's'} ahead of the nearest cycle. "
                    "It will automatically re-anchor and update as earlier real "
                    "restocks/depletions are observed."
                ),
                inline=False,
            )

        if reliability in {"unreliable", "insufficient"}:
            guidance = (
                "Best estimate only. The historical travel success is not strong "
                "enough to treat this as confident departure guidance."
            )
            if active.get("arrival_offset_source") == "mid-stock fallback":
                guidance += (
                    " Arrival/leave-by currently target the midpoint of typical stock "
                    "lifetime until enough resolved trips exist to learn a better offset."
                )
            embed.add_field(
                name="🚨 Guidance",
                value=guidance,
                inline=False,
            )
    else:
        embed.description = (
            f"⚫ **No reachable active travel target**\n"
            f"📦 Current stock: **{stock_text}**\n"
            f"{reliability_emoji} Travel reliability: **{reliability.upper()}**"
        )
        chain_lines = _prediction_chain_lines(result)
        embed.add_field(
            name="🔭 Available estimates",
            value="\n".join(chain_lines) if chain_lines else "No forecast cycles available yet.",
            inline=False,
        )

    # Current-stock reachability is useful when stock is already up.
    if result.get("current_stock", 0) > 0 and result.get("current_stock_estimated_reachable") is not None:
        if result.get("current_stock_estimated_reachable"):
            current_value = (
                f"✅ Current stock may still be available on arrival.\n"
                f"ETA if leaving now: {_discord_time(result.get('current_stock_eta_if_leave_now_timestamp'), 't')}\n"
                f"Estimated depletion: {_discord_time(result.get('estimated_current_depletion_timestamp'), 't')}"
            )
        else:
            current_value = (
                "❌ Current stock is not expected to survive until arrival if leaving now."
            )
        embed.add_field(name="📦 Current-stock check", value=current_value, inline=False)

    active_number = (active or {}).get("prediction_number")
    chain_lines = _prediction_chain_lines(result, active_number=active_number)
    if chain_lines:
        # Keep Discord readable: show the forecast chain up through the active
        # target plus one backup cycle (the live service already caps this).
        embed.add_field(
            name="🧭 Reachable-cycle forecast",
            value="\n".join(chain_lines),
            inline=False,
        )

    evidence = (result.get("model_evidence_tier") or "—").upper()
    model = (active or {}).get("model_name") or result.get("model_name") or "—"
    note = result.get("note") or ""
    footer = f"Model evidence: {evidence} · Model: {model}"
    if note:
        # Keep Discord footer compact; detailed status is already visible in fields.
        footer += " · Prediction v2"
    embed.set_footer(text=footer[:2048])

    return embed
