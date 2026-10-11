"""V91: pure, offline-only research prototype for TORN travel decision views.

Three views of the SAME candidate opportunities:
- leave_now: all plausible research proposals with departure <= user urgency.
- next_opportunity: earliest viable departure per item, even when much later.
- best_chance: rank only supported arrival-stock-margin estimates; never infer
  calibrated success rates from a research-only forecast.

Not mounted to web, used by workers, or linked to gameplay actions. Requires
independently generated alternative candidates per item to show genuinely
different options; existing 24 research specialists usually provide only one.
Stock, probability and survival estimates are never fabricated by this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

# Mirrors pinned model travel contract for validation only, NOT a travel planner.
TRAVEL_SECONDS = {
    "mex":1020, "cay":1380, "can":1620, "haw":5340, "uni":6360,
    "arg":6660, "swi":6960, "jap":8940, "chi":9600, "uae":10800,
    "sou":11820,
}
CATEGORIES = frozenset({"flowers", "plushies", "medical", "fossils", "other"})
MODES = frozenset({"leave_now", "next_opportunity", "best_chance"})
FORECAST_STATUSES = frozenset({"RESEARCH_PROPOSAL_ONLY", "FORWARD_CANDIDATE_ONLY"})
EVIDENCE_TIERS = {"research":0, "forward_observed":1, "validated":2}
FLOWERS_IN_24 = frozenset({
    "Ceibo Flower", "Crocus", "Banana Orchid", "Peony", "Orchid",
    "Cherry Blossom", "Dahlia", "African Violet", "Edelweiss",
    "Tribulus Omanense", "Heather",
})
MAX_SOURCE_AGE = 180
MAX_MODEL_WAIT = 28800
DEFAULT_QUICK_SECONDS = 300
MAX_QUICK_SECONDS = 3600


def item_category(item_key: str, category_from_catalog: str | None = None) -> str:
    """Prefer a trusted catalog category; never call unrecognized items flowers."""
    if category_from_catalog is not None:
        if category_from_catalog not in CATEGORIES:
            raise ValueError("unknown catalog category")
        return category_from_catalog
    item = item_key.split(":",1)[-1]
    if item.endswith(" Plushie"):
        return "plushies"
    if item in ("Xanax",):
        return "medical"
    if "Fossil" in item or item.endswith(" Fossil"):
        return "fossils"
    if item in FLOWERS_IN_24:
        return "flowers"
    return "other"


@dataclass(frozen=True)
class Opportunity:
    item_key: str
    model_id: str
    issued_at: int
    stock_as_of: int
    valid_until: int
    depart_at: int
    arrive_at: int
    status: str = "RESEARCH_PROPOSAL_ONLY"
    category: str | None = None
    threshold: int = 30
    grace_seconds: int = 10
    evidence_tier: str = "research"
    # Fields below must be grounded in a recorded model output or evaluated
    # validation artifact. None MUST remain None if source cannot supply them.
    projected_stock_floor: int | None = None
    projected_survival_minutes: float | None = None
    calibrated_success_probability: float | None = None
    independent_calibration_sample_size: int | None = None
    revision_magnitude_seconds: int | None = None
    provider_update_as_of: int | None = None

    def resolved_category(self):
        return item_category(self.item_key,self.category)


def validity(candidate: Opportunity, now: int):
    """Return one reason, or None if an as-issued candidate is still displayable."""
    if not isinstance(candidate, Opportunity):
        return "INVALID_CONTRACT"
    country, sep, item = candidate.item_key.partition(":")
    if not sep or not item or country not in TRAVEL_SECONDS or not candidate.model_id:
        return "INVALID_ITEM"
    if candidate.status not in FORECAST_STATUSES:
        return "INVALID_STATUS"
    if candidate.evidence_tier not in EVIDENCE_TIERS:
        return "INVALID_EVIDENCE_TIER"
    try:
        if candidate.resolved_category() not in CATEGORIES:
            return "INVALID_CATEGORY"
    except (ValueError, TypeError):
        return "INVALID_CATEGORY"
    times=(candidate.issued_at,candidate.stock_as_of,candidate.valid_until,
           candidate.depart_at,candidate.arrive_at,now)
    if any(type(t) is not int for t in times):
        return "INVALID_TIMESTAMP"
    if candidate.threshold!=30 or candidate.grace_seconds!=10:
        return "INCOMPATIBLE_THRESHOLD_CONTRACT"
    if not candidate.stock_as_of<=candidate.issued_at<=now:
        return "FUTURE_OR_INCONSISTENT_EVIDENCE"
    if candidate.issued_at-candidate.stock_as_of>MAX_SOURCE_AGE:
        return "STALE_COLLECTOR_AT_ISSUE"
    if now-candidate.stock_as_of>MAX_SOURCE_AGE:
        return "STALE_COLLECTOR_NOW"
    if candidate.valid_until<=now:
        return "EXPIRED_SNAPSHOT"
    if candidate.valid_until-candidate.issued_at>900:
        return "UNBOUNDED_SNAPSHOT_TTL"
    if not now<=candidate.depart_at<=candidate.issued_at+MAX_MODEL_WAIT:
        return "DEPARTURE_PASSED_OR_TOO_FAR"
    if candidate.arrive_at-candidate.depart_at!=TRAVEL_SECONDS[country]:
        return "TRAVEL_TIME_MISMATCH"
    if candidate.provider_update_as_of is not None:
        u=candidate.provider_update_as_of
        if type(u) is not int or u>candidate.stock_as_of:
            return "BAD_PROVIDER_UPDATE_TIMESTAMP"
        if candidate.stock_as_of-u>MAX_SOURCE_AGE or now-u>MAX_SOURCE_AGE:
            return "STALE_PROVIDER_UPDATE"
    if (candidate.projected_stock_floor is not None and
        (type(candidate.projected_stock_floor) is not int or
         candidate.projected_stock_floor<0)):
        return "INVALID_STOCK_FLOOR"
    if (candidate.projected_survival_minutes is not None and
        (not isinstance(candidate.projected_survival_minutes,(int,float)) or
         not 0<=candidate.projected_survival_minutes<=1e6)):
        return "INVALID_SURVIVAL_ESTIMATE"
    if (candidate.revision_magnitude_seconds is not None and
        (type(candidate.revision_magnitude_seconds) is not int or
         candidate.revision_magnitude_seconds<0)):
        return "INVALID_REVISION"
    if candidate.calibrated_success_probability is not None:
        p=candidate.calibrated_success_probability
        n=candidate.independent_calibration_sample_size
        if (not isinstance(p,(int,float)) or not 0<=p<=1 or
            candidate.evidence_tier!="validated" or
            type(n) is not int or n<=0):
            return "UNSUPPORTED_CALIBRATED_PROBABILITY"
    if (candidate.projected_stock_floor is not None and
        candidate.projected_stock_floor<candidate.threshold):
        return "PREDICTED_STOCK_BELOW_THRESHOLD"
    return None


def exposure_label(c: Opportunity, now: int, quick_seconds=DEFAULT_QUICK_SECONDS):
    """A research preview is NEVER labeled a verified departure instruction."""
    within_quick = c.depart_at-now<=quick_seconds
    has_stock_bound=(c.projected_stock_floor is not None and
                     c.projected_stock_floor>=c.threshold)
    has_provider_freshness=c.provider_update_as_of is not None
    if (within_quick and c.evidence_tier=="validated" and has_stock_bound
        and has_provider_freshness):
        return "QUALIFIED_DEPARTURE_WINDOW"
    if within_quick:
        return "PROVISIONAL_NEAR_TERM"
    return "FUTURE_WATCH"


def _wait(c: Opportunity, now: int) -> int:
    return c.depart_at-now


def _margin(c: Opportunity) -> int:
    return -1 if c.projected_stock_floor is None else c.projected_stock_floor-c.threshold


def _survival(c: Opportunity) -> float:
    return -1.0 if c.projected_survival_minutes is None else float(c.projected_survival_minutes)


def _stability(c: Opportunity) -> int:
    return 86400 if c.revision_magnitude_seconds is None else c.revision_magnitude_seconds


def _earliest_sort(c: Opportunity, now: int):
    # Speed first; break ties with safer stock reserve/stability only if known.
    return (_wait(c,now), -_margin(c), -_survival(c), _stability(c),
            c.item_key,c.model_id)


def _quality_sort(c: Opportunity, now: int):
    # Credible calibrated success (when it exists) outranks research-only
    # stocks. Uncalibrated percentages must never be invented.
    p=c.calibrated_success_probability
    return (0 if p is not None else 1,
            -(p if p is not None else -1),
            -EVIDENCE_TIERS[c.evidence_tier],
            -_margin(c), -_survival(c), _stability(c),
            _wait(c,now), c.item_key, c.model_id)


def evaluate_views(candidates: Iterable[Opportunity], *, now: int,
                   category: str | None = None,
                   quick_seconds: int = DEFAULT_QUICK_SECONDS):
    """Return JSON-compatible per-view choices. Never infers new departures."""
    if type(now) is not int or type(quick_seconds) is not int or not (
        0<=quick_seconds<=MAX_QUICK_SECONDS):
        raise ValueError("invalid now or urgency window")
    if category is not None and category not in CATEGORIES:
        raise ValueError("unknown category")
    accepted=[]
    exclusions=Counter()
    for c in candidates:
        if not isinstance(c,Opportunity):
            exclusions["INVALID_CONTRACT"]+=1
            continue
        reason=validity(c,now)
        if reason is None and category is not None and c.resolved_category()!=category:
            continue
        if reason is None:
            accepted.append(c)
        else:
            exclusions[reason]+=1

    def pack(c):
        return {
            "item_key":c.item_key,
            "category":c.resolved_category(),
            "model_id":c.model_id,
            "depart_at":c.depart_at,"arrive_at":c.arrive_at,
            "wait_seconds":_wait(c,now),
            "issued_at":c.issued_at,"valid_until":c.valid_until,
            "evidence_tier":c.evidence_tier,
            "exposure":exposure_label(c,now,quick_seconds),
            "projected_stock_floor":c.projected_stock_floor,
            "stock_reserve_above_30":(
                _margin(c) if c.projected_stock_floor is not None else None),
            "projected_survival_minutes":c.projected_survival_minutes,
            "calibrated_success_probability":c.calibrated_success_probability,
            "independent_calibration_sample_size":c.independent_calibration_sample_size,
            "revision_magnitude_seconds":c.revision_magnitude_seconds,
            "provider_update_as_of":c.provider_update_as_of,
            "accuracy_verified":c.evidence_tier=="validated",
            "experimental":c.evidence_tier!="validated",
        }

    def one_per_item(ordered):
        chosen={}
        for c in ordered:
            chosen.setdefault(c.item_key,c)
        return list(chosen.values())

    fast=one_per_item(sorted(
        (c for c in accepted if _wait(c,now)<=quick_seconds),
        key=lambda c:_earliest_sort(c,now)))
    nexts=one_per_item(sorted(accepted,key=lambda c:_earliest_sort(c,now)))
    # Stock margin needed before "best" means more than an unsupported hunch.
    quality_qualified=[c for c in accepted
                       if c.projected_stock_floor is not None]
    best=one_per_item(sorted(quality_qualified,
                            key=lambda c:_quality_sort(c,now)))
    return {
        "status":"RESEARCH_ONLY_NOT_FOR_GAMEPLAY_AUTOMATION",
        "now":now,"quick_window_seconds":quick_seconds,
        "category_filter":category,
        "source_candidate_count":len(accepted)+sum(exclusions.values()),
        "valid_candidate_count":len(accepted),
        "excluded_by_reason":dict(sorted(exclusions.items())),
        "leave_now":[pack(c) for c in fast],
        "next_opportunity":[pack(c) for c in nexts],
        "best_chance":[pack(c) for c in best],
        "best_chance_warning":(
            "Stock-margin proxy ranking only; not a calibrated hit rate"
            if best and any(c.calibrated_success_probability is None for c in best)
            else ("Calibrated sample sizes vary; not guaranteed game availability"
                  if best else "No supplied stock-floor estimates; cannot rank best chance")),
        "alternative_generation_complete":False,
        "note":"Each supplied candidate is an as-issued proposal, not an executed flight. Existing specialists usually expose one option. No gameplay commands or probability estimates are generated.",
    }
