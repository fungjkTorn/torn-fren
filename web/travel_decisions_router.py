"""Additive OFF-by-default research routes; precomputed snapshot only."""
import os
import time
from pathlib import Path

from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import FileResponse
from services.travel_read_model import SnapshotCache,build_board

router=APIRouter()
cache=SnapshotCache()


def enabled():
    if os.environ.get("TORN_FREN_TRAVEL_DECISIONS_BETA")!="1":
        raise HTTPException(status_code=404,detail="Travel Decisions beta disabled")


@router.get("/travel-decisions",include_in_schema=False)
def page():
    enabled()
    return FileResponse(Path(__file__).with_name("travel_decisions.html"))


@router.get("/api/travel-decisions")
def board(country:str|None=None,flight_seconds:int|None=Query(default=None,ge=60,le=86400)):
    enabled()
    if bool(country)!=(flight_seconds is not None):
        raise HTTPException(status_code=400,detail="Choose a country with a flight duration")
    location=os.environ.get("TORN_FREN_TRAVEL_EVENT_SNAPSHOT")
    if not location:
        return {"status":"NO_EVENT_SNAPSHOT","rows":[],"item_count":0}
    try:
        snapshot=cache.read(location)
        if country and not any(k.startswith(country+":") for k in snapshot.get("items",{})):
            raise ValueError("unsupported country")
        return build_board(snapshot,now=int(time.time()),
                           flight_overrides={country:flight_seconds} if country else None)
    except (OSError,ValueError,TypeError,KeyError):
        raise HTTPException(status_code=503,detail="Travel forecast unavailable; recheck later")
