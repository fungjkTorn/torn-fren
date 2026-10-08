"""Opt-in token-protected READ-ONLY research endpoint; disabled by default.

The route never changes the existing /api/history Prediction V2 route.
Token must be sent via X-Torn-Fren-Shadow-Token header (not URL query).
"""
from __future__ import annotations
import os
from fastapi import APIRouter, Header, HTTPException, Query
from services.private_champion_shadow_v29 import (
    ENABLED_ENV, make_shadow_snapshot, ShadowUnavailable, ShadowUnauthorized,
)

router = APIRouter()


@router.get("/api/research/champion-shadow")
def champion_shadow(
    country: str = Query(..., min_length=3, max_length=3),
    item: str = Query(..., min_length=1, max_length=120),
    private_token: str | None = Header(default=None, alias="X-Torn-Fren-Shadow-Token"),
):
    if os.environ.get(ENABLED_ENV, "").strip().lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return make_shadow_snapshot(country, item, private_token)
    except ShadowUnauthorized:
        raise HTTPException(status_code=403, detail="Forbidden")
    except ShadowUnavailable:
        raise HTTPException(status_code=503, detail="Research shadow unavailable")
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown catalog item")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item")
