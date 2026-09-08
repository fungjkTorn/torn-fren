import requests

class TornAPI:
    """
    Thin wrapper around the official Torn API v1 (https://api.torn.com).
    Endpoints are organized by category: user, faction, market, torn, property, company.
    """
    BASE_URL = "https://api.torn.com"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _request(self, category: str, selections: str = "", id: str = ""):
        """
        Makes a GET request to a Torn API category and returns parsed JSON.
        Torn wraps API errors in an {"error": {...}} object with HTTP 200.
        """
        url = f"{self.BASE_URL}/{category}/{id}"
        params = {
            "selections": selections,
            "key": self.api_key,
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            return {"error": f"Request failed: {e}"}

        data = response.json()
        if "error" in data:
            return {"error": data["error"]}
        return data

    def user(self, selections: str = "basic", id: str = ""):
        return self._request("user", selections=selections, id=id)

    def faction(self, selections: str = "basic", id: str = ""):
        return self._request("faction", selections=selections, id=id)

    def market(self, selections: str = "bazaar", id: str = ""):
        return self._request("market", selections=selections, id=id)

    def torn(self, selections: str = "", id: str = ""):
        return self._request("torn", selections=selections, id=id)