"""V145 research challenger: preserve explicitly observed stock phases across
benign provider switches without making cross-provider restock claims.

Key user requirement: A completed stocked/depleted phase should be usable if
its START and END transitions are directly observed, even when sources switch
in the MIDDLE without disagreeing on whether quantity >=30.

Existing V128 resets an otherwise known phase_start at ANY provider change.
That can cause CURRENT_PHASE_ONSET_UNKNOWN even if source A saw a clean restock,
source B continued to show in-stock and source A/B later saw a clean sellout.

This is an additive, pure, past-only challenger. No production/research shadow
worker, model, ledger, collector, or website is changed or auto-promoted.
"""
from __future__ import annotations

from collections import Counter

from research.v128_full24_earliest_shadow import (
    MIN_QTY, _gap_index,
)


def provider_continuous_phases(observations, *, asof, gaps=()):
    """Return V128-compatible durations plus explicit transition diagnostics.

    Eligible starts/ends are observed consecutive-row threshold crossings
    within ONE provider on both sides of each crossing, with NO collector
    gap. A provider switch in the middle of a period doesn't invalidate
    that period if both endpoints of the switch agree on stock threshold.

    A cross-provider threshold contradiction is ambiguous: do not construct
    a phase onset or completed duration from it. A known gap or a timestamp
    regression resets phase onset, independently of provider.

    No lookahead, inferred missing transitions, or fabricated event times.
    """
    if type(asof) is not int or asof <= 0:
        raise ValueError("invalid as-of epoch")
    crosses_gap = _gap_index(gaps, asof)
    last = None
    current = None
    onset = None
    completed_high = []
    completed_low = []
    c = Counter()
    for obs in observations:
        if obs.epoch > asof:
            raise ValueError("future stock observation")
        if (type(obs.epoch) is not int or type(obs.quantity) is not int
            or obs.quantity < 0 or not obs.source):
            c["invalid_observation"] += 1
            continue
        high = obs.quantity >= MIN_QTY
        if last is None:
            current, onset = high, None
        else:
            ordered = obs.epoch > last.epoch
            gap = crosses_gap(last.epoch, obs.epoch) if ordered else False
            source_switch = obs.source != last.source
            if not ordered or gap:
                c["restarted_after_gap_or_clock"] += 1
                current, onset = high, None
            elif source_switch and high != current:
                # An observed high/low disagreement ON the provider switch
                # is not a proven restock/depletion boundary.
                c["cross_source_threshold_conflict"] += 1
                current, onset = high, None
            else:
                if source_switch:
                    c["benign_provider_switches_preserved"] += 1
                if high != current:
                    # Both consecutive observations are from the same
                    # provider, so we have a directly observed transition.
                    c["clean_observed_threshold_crossings"] += 1
                    if onset is not None and obs.epoch > onset:
                        (completed_high if current else completed_low).append(
                            obs.epoch - onset
                        )
                        c["completed_phases_with_observed_boundaries"] += 1
                    current, onset = high, obs.epoch
        last = obs
    return {
        "phase": (
            "HIGH" if current is True else
            "LOW" if current is False else "UNKNOWN"
        ),
        "phase_onset": onset,
        "last_observation": last,
        "stocked_durations": completed_high,
        "depleted_durations": completed_low,
        "diagnostics": dict(sorted(c.items())),
        "only_observed_clean_phase_boundaries": True,
        "historical_provider_switch_in_middle_allowed": True,
        "cross_provider_phase_transition_inferred": False,
        "source_country_freshness_verified": False,
    }



def observed_cycle_evidence_tier(phases, *, required_for_monte_carlo=5):
    """Any genuinely completed observed phase counts as historical evidence.

    Unlike the V128 >=5+5 Monte Carlo eligibility rule, a single bounded
    stocked interval is not thrown away as 'no history.' Sparse periods
    are valid research evidence, but do NOT authorize a high-confidence
    departure recommendation or fabricated inferred missing periods.
    """
    if (not isinstance(phases,dict) or
        type(required_for_monte_carlo) is not int
        or required_for_monte_carlo < 2):
        raise ValueError("invalid evidence tier arguments")
    highs=phases.get("stocked_durations")
    lows=phases.get("depleted_durations")
    if (not isinstance(highs,list) or not isinstance(lows,list)
        or any(type(x) is not int or x <= 0 for x in highs+lows)):
        raise ValueError("invalid completed phase durations")
    high_n=len(highs)
    low_n=len(lows)
    if high_n >= required_for_monte_carlo and low_n >= required_for_monte_carlo:
        tier="V128_MONTE_CARLO_SAMPLE_ELIGIBLE"
    elif high_n > 0 and low_n > 0:
        tier="BOUNDED_HISTORY_SPARSE_PROVISIONAL"
    elif high_n > 0 or low_n > 0:
        tier="ONE_PHASE_KIND_OBSERVED_NO_CLOSED_FULL_CYCLE"
    else:
        tier="NO_COMPLETED_BOUNDED_INTERVALS"
    return {
        "tier":tier,
        "observed_bounded_stocked_intervals":high_n,
        "observed_bounded_depleted_intervals":low_n,
        "min_samples_per_phase_for_existing_v128_curve":required_for_monte_carlo,
        "history_exists":high_n > 0 or low_n > 0,
        "supports_valid_completed_stocked_lifetime":high_n > 0,
        "supports_valid_completed_depleted_wait":low_n > 0,
        "sufficient_for_existing_v128_monte_carlo": (
            tier=="V128_MONTE_CARLO_SAMPLE_ELIGIBLE"
        ),
        "arrival_recommendation_accuracy_established":False,
        "permission_to_publish_as_certified_departure":False,
    }


def compare_phase_eligibility(observations, *, asof, gaps=()):
    """One-clock-tick comparison, NOT an accuracy or deployment result."""
    from research.v128_full24_earliest_shadow import fast_phases
    old = fast_phases(observations, asof=asof, gaps=gaps)
    improved = provider_continuous_phases(
        observations, asof=asof, gaps=gaps
    )
    return {
        "old_phase_onset_known": old["phase_onset"] is not None,
        "new_phase_onset_known": improved["phase_onset"] is not None,
        "old_completed_stocked": len(old["stocked_durations"]),
        "new_completed_stocked": len(improved["stocked_durations"]),
        "old_completed_depleted": len(old["depleted_durations"]),
        "new_completed_depleted": len(improved["depleted_durations"]),
        "new_diagnostics": improved["diagnostics"],
        "safety": "RESEARCH_ONLY_NO_FORWARD_ACCURACY_CLAIM",
    }
