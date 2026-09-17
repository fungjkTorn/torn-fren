from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from services.history_service import get_item_history_since

app = FastAPI()

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/history")
def api_history(country: str = Query(...), item: str = Query(...), minutes: int = Query(1440)):
    hours = minutes / 60
    rows = get_item_history_since(country, item, hours)
    return {"country": country, "item": item, "minutes": minutes, "rows": rows}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")