"""
The only place that decides where travel stock data comes from.
Everything else (poller, modules/stock.py) never needs to know whether
data came from YATA or Prometheus.
"""

from services import yata_api
from services import prometheus_api


def _is_valid_export(data):
    """A valid export must have a non-empty 'stocks' dict."""
    return bool(data) and bool(data.get("stocks"))


def get_travel_export():
    """
    Returns normalized travel stock data:
    {
        "source": "yata" or "prometheus",
        "timestamp": 1234567890,
        "stocks": {
            "uni": {"update": 1234567890, "stocks": [{"id": .., "name": .., "quantity": .., "cost": ..}, ...]},
            ...
        }
    }
    Returns None if every provider fails.
    """
    print("Fetching travel stock from YATA...")
    yata_data = yata_api.get_travel_export()

    if _is_valid_export(yata_data):
        print("YATA success.")
        return {
            "source": "yata",
            "timestamp": yata_data.get("timestamp"),
            "stocks": yata_data.get("stocks", {}),
        }

    print("YATA failed.")
    print("Trying Prometheus...")

    prometheus_data = prometheus_api.get_travel_export()

    if _is_valid_export(prometheus_data):
        print("Prometheus success.")
        return {
            "source": "prometheus",
            "timestamp": prometheus_data.get("timestamp"),
            "stocks": prometheus_data.get("stocks", {}),
        }

    print("Prometheus failed.")
    print("No travel export available this cycle.")
    return None