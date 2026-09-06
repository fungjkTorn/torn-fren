# Knows nothing about Discord — just answers "what do we know about this place?"

TRAVEL_DATA = {
    "argentina": {
        "flag": "🇦🇷",
        "name": "Argentina",
        "travel_time": "26 minutes",
        "items": ["Teddy Bears", "Red Roses"],
    },
    "mexico": {
        "flag": "🇲🇽",
        "name": "Mexico",
        "travel_time": "18 minutes",
        "items": ["Alcohol", "Estrogen"],
    },
}

def get_travel_info(country: str):
    return TRAVEL_DATA.get(country.lower())