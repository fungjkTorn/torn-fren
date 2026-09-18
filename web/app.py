from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from services.history_service import get_item_history_since, get_stock_graph_analysis

app = FastAPI(title="Torn Fren Stock Graph")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/history")
def api_history(
    country: str = Query(..., min_length=3, max_length=3),
    item: str = Query(..., min_length=1),
    minutes: int = Query(1440, ge=1, le=10080),
):
    country = country.lower().strip()
    item = item.strip()

    if not item:
        raise HTTPException(status_code=400, detail="Item name is required.")

    hours = minutes / 60
    rows = get_item_history_since(country, item, hours)
    analysis = get_stock_graph_analysis(country, item, hours)

    return {
        "country": country,
        "item": item,
        "minutes": minutes,
        "rows": rows,
        "analysis": analysis,
    }


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
