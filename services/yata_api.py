import requests

YATA_EXPORT_URL = "https://yata.yt/api/v1/travel/export/"


def get_country_stock(country_code: str):
    """
    Calls YATA's travel export endpoint and returns the stock list for one country.

    Returns a list of dicts like:
        [{"id": 180, "name": "Teddy Bear", "quantity": 1860, "cost": 4200}, ...]
    or an empty list if the country code doesn't match anything, or the request fails.
    """
    try:
        response = requests.get(YATA_EXPORT_URL, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"YATA request failed: {e}")
        return []

    data = response.json()
    country_data = data.get("stocks", {}).get(country_code, {})
    return country_data.get("stocks", [])


if __name__ == "__main__":
    # Quick manual test: python services/yata_api.py
    stock = get_country_stock("uk")
    for item in stock:
        print(f"{item['name']}: {item['quantity']} (${item['cost']})")