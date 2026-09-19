from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from services.history_service import get_item_history_since, get_stock_graph_analysis
from services.prediction_v2_live import build_live_prediction_v2

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

    # Prediction v2 is isolated from the base history analysis so a model-side
    # issue cannot take the graph down.  The old prediction is retained as
    # baseline_prediction for diagnostics.
    try:
        prediction_v2 = build_live_prediction_v2(country, item)
        analysis["baseline_prediction"] = analysis.get("prediction")
        analysis["prediction_v2"] = prediction_v2

        display = prediction_v2.get("display_prediction") if prediction_v2 else None
        if display and display.get("estimate_timestamp"):
            # Compatibility shape used by the existing chart overlay.
            analysis["prediction"] = {
                **display,
                "confidence": display.get("travel_reliability"),
                "sample_count": prediction_v2.get("model_evidence_tier"),
                "excluded_sample_count": None,
                "note": prediction_v2.get("note"),
            }
    except Exception as exc:
        analysis["prediction_v2_error"] = str(exc)

    return {
        "country": country,
        "item": item,
        "minutes": minutes,
        "rows": rows,
        "analysis": analysis,
    }


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
