import requests

YATA_EXPORT_URL = "https://yata.yt/api/v1/travel/export/"


def get_travel_export():
    """
    Calls YATA's travel export endpoint once and returns the full response.
    """
    try:
        response = requests.get(YATA_EXPORT_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"YATA request failed: {e}")
        return {}
    except ValueError:
        print("YATA returned invalid JSON.")
        return {}


def get_country_data(country_code: str):
    """
    Returns the raw YATA data for one country.
    """
    data = get_travel_export()
    return data.get("stocks", {}).get(country_code, {})


def get_country_stock(country_code: str):
    """
    Returns the stock list for one country.
    """
    country_data = get_country_data(country_code)
    return country_data.get("stocks", [])


def get_country_update_time(country_code: str):
    """
    Returns YATA's last update timestamp for the country.
    """
    country_data = get_country_data(country_code)
    return country_data.get("update")


if __name__ == "__main__":
    stock = get_country_stock("uni")
    for item in stock:
        print(f"{item['name']}: {item['quantity']} (${item['cost']:,})")