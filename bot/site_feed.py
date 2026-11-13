"""Read the same precomputed, evidence-gated travel decisions as the public website.

No prediction fitting, model selection, or writes to the collector happen here.
"""
from __future__ import annotations

import json
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


class FeedUnavailable(RuntimeError):
    """Website feed is missing, stale, invalid or unreachable."""


ALLOWED_DECISIONS = {
    "WAIT_FOR_ESTIMATED_DEPARTURE",
    "ESTIMATED_DEPARTURE_WINDOW_OPEN",
}
MAX_FEED_BYTES = 8 * 1024 * 1024


def site_url(base_url, path="/", *, country=None, item=None):
    base = (base_url or "").rstrip("/")
    if not base:
        return None
    suffix = path if path.startswith("/") else "/" + path
    url = base + suffix
    if country and item:
        url += "?" + urlencode({"country": country, "item": item})
    return url


def fetch_board(base_url, *, now=None, timeout=5):
    """Fetch the *published* beta snapshot. Never fall back to old V2."""
    if not base_url:
        raise FeedUnavailable("PUBLIC_BASE_URL is not configured")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        raise FeedUnavailable("Website feed requires HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise FeedUnavailable("Invalid website base URL")
    url = site_url(base_url, "/api/first-release")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "TornFren-Discord/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_FEED_BYTES + 1)
        if len(data) > MAX_FEED_BYTES:
            raise FeedUnavailable("Website feed exceeds size limit")
        board = json.loads(data)
    except (OSError, ValueError, TimeoutError) as exc:
        raise FeedUnavailable("Website prediction feed is unavailable") from exc
    if not isinstance(board, dict) or not isinstance(board.get("rows"), list):
        raise FeedUnavailable("Website prediction feed is invalid")
    if board.get("status") not in {"LIVE_BETA", "STALE_DATA"}:
        raise FeedUnavailable("Website prediction feed is not ready")
    issued = board.get("published_epoch")
    timestamp = int(time.time() if now is None else now)
    if type(issued) is not int or issued > timestamp + 15:
        raise FeedUnavailable("Website publication clock is invalid")
    return board


def item_row(board, country, item):
    key = country.lower().strip() + ":" + item.casefold().strip()
    for row in board.get("rows", []):
        if isinstance(row, dict) and str(row.get("item_key", "")).casefold() == key:
            return row
    return None


def row_status(row, *, now=None):
    """An approved row need not currently have a usable departure.

    The original ten and challenger cohort have separate freshness gates.
    Do not use the global board status as a substitute for the row gate.
    """
    if row is None:
        return "UNDER_REVIEW"
    if not isinstance(row, dict):
        return "UNAVAILABLE"
    timestamp = int(time.time() if now is None else now)
    until = row.get("valid_until_epoch")
    if type(until) is not int or timestamp > until:
        return "STALE_DATA"
    decision = row.get("decision") or {}
    status = decision.get("status", "UNAVAILABLE")
    if status not in ALLOWED_DECISIONS:
        return str(status)
    depart = decision.get("estimated_departure_epoch")
    arrive = decision.get("estimated_arrival_epoch")
    deadline = decision.get("estimated_departure_deadline_epoch")
    flight = decision.get("player_flight_seconds")
    if any(type(v) is not int for v in (depart, arrive, deadline, flight)):
        return "UNAVAILABLE"
    if depart > deadline or arrive != depart + flight or deadline < timestamp:
        return "UNAVAILABLE"
    return status


def known_rate(row):
    """Only the new live-beta simulated-trip evidence is eligible to display."""
    if not row:
        return None
    evidence = row.get("live") or {}
    audit = evidence.get("target_identity_audit") or {}
    if audit.get("duplicate_target_groups", 0):
        return None
    if evidence.get("rate_status") not in (None, "KNOWN_SIMULATED_TRIPS"):
        return None
    fraction = evidence.get("success_fraction")
    known = evidence.get("known", 0)
    if type(fraction) not in (float, int) or not 0 <= fraction <= 1 or type(known) is not int or known <= 0:
        return None
    return f"{fraction * 100:.0f}% ({evidence.get('successes', 0)}/{known} known simulated trips)"


def format_epoch(epoch):
    return f"<t:{epoch}:F> (<t:{epoch}:R>)" if type(epoch) is int and epoch > 0 else "Unavailable"


def format_prediction(country, item, row, *, now=None):
    """Discord-safe text; never transform under-review models into advice."""
    key = f"**{item} — {country.upper()}**"
    status = row_status(row, now=now)
    if row is None:
        return key + "\n⚪ **Under review:** no approved live departure forecast yet. Use /stock or the website graph for observations."
    if status == "STALE_DATA":
        return key + "\n⚠️ **Forecast data stale.** No departure recommendation is being shown."
    decision = row.get("decision") or {}
    if status not in ALLOWED_DECISIONS:
        return key + f"\n⚪ **No actionable departure:** {status.replace('_', ' ')}. Check the website for observations."
    kind = "current stock" if decision.get("selected_restock_event_index") == 0 else "a forecasted buying window"
    evidence = row.get("live") or {}
    rate = known_rate(row)
    lines = [
        key,
        "🧭 **Live-beta forecast** — targets **more than 30 items at landing**.",
        f"🎯 Target: {kind}",
        f"🛫 **Depart:** {format_epoch(decision['estimated_departure_epoch'])}",
        f"⏰ **Estimated departure deadline:** {format_epoch(decision['estimated_departure_deadline_epoch'])}",
        f"🛬 **Target arrival:** {format_epoch(decision['estimated_arrival_epoch'])}",
        f"📋 Status: **{status.replace('_', ' ')}**",
        f"📊 Last 10: **{rate}**" if rate else
            f"📊 Last 10: collecting/under review (known={evidence.get('known', 0)}, pending={evidence.get('pending', 0)}, unknown={evidence.get('unknown', 0)})",
        f"🔬 Evidence: **forward simulated trips**; not confirmed player-flight success.",
        f"🕒 Forecast valid until: {format_epoch(row.get('valid_until_epoch'))}",
    ]
    return "\n".join(lines)


def fetch_history_summary(base_url, country, item, *, timeout=5):
    if not base_url:
        raise FeedUnavailable("PUBLIC_BASE_URL is not configured")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        raise FeedUnavailable("Website history requires HTTPS")
    url = site_url(base_url, "/api/first-release/history-summary", country=country, item=item)
    try:
        with urlopen(Request(url, headers={"Accept": "application/json", "User-Agent": "TornFren-Discord/1"}), timeout=timeout) as response:
            data = response.read(65_537)
        if len(data) > 65_536:
            raise FeedUnavailable("History response exceeds limit")
        result = json.loads(data)
    except (OSError, ValueError, TimeoutError) as exc:
        raise FeedUnavailable("Website observed history is unavailable") from exc
    if not isinstance(result, dict):
        raise FeedUnavailable("Invalid observed history response")
    return result


def _duration(seconds):
    if type(seconds) not in (int, float) or seconds < 0:
        return "Unavailable"
    hours, remainder = divmod(int(seconds), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def format_history(country, item, summary, row):
    header = f"📚 **{item} — {country.upper()}**"
    if summary.get("status") != "AVAILABLE":
        return header + "\nObserved-history sample unavailable. This does not imply a supported prediction."
    return "\n".join([
        header, "**Observed availability history** (stock >30; descriptive, not forecast accuracy)",
        f"🟢 Last observed availability opening: {format_epoch(summary.get('last_restock_timestamp'))}",
        f"📦 Typical stocked time (median): {_duration(summary.get('median_stocked_seconds'))}",
        f"⌛ Typical below-threshold time (median): {_duration(summary.get('median_unstocked_seconds'))}",
        f"📊 Completed stocked windows: {summary.get('completed_stock_windows', 0)}",
        f"⚠️ Uncertain boundaries: {summary.get('uncertain_boundaries', 0)}",
        f"🕒 Sample end: {format_epoch(summary.get('sample_end_epoch'))}",
        f"🎯 Model status: **{row_status(row).replace('_', ' ')}**",
        "Use /predict for the published trip decision; history statistics are not success rates.",
    ])
