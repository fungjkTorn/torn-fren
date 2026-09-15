import requests

PROMETHEUS_URL = "https://api.prombot.co.uk/api/travel"


def get_travel_export():
    """
    Calls Prometheus's travel endpoint (confirmed via manual testing —
    see test_prometheus.py) and returns the full response.

    Shape matches YATA closely:
    {
        "stocks": {
            "mex": {
                "update": 1789431355,
                "stocks": [
                    {"id": 229, "name": "Claymore Mine", "quantity": 0, "cost": 15000, "nextRestock": "2026-09-14T23:45:00.000Z"},
                    ...
                ]
            },
            ...
        }
    }

    Note: Prometheus includes an extra "nextRestock" field per item (ISO 8601
    timestamp or null) that YATA doesn't have. We don't store it yet — no schema
    change for this update — save_snapshot_from_export just ignores fields it
    doesn't recognize (id/name/quantity/cost only).
    """
    try:
        response = requests.get(PROMETHEUS_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Prometheus request failed: {e}")
        return {}
    except ValueError:
        print("Prometheus returned invalid JSON.")
        return {}