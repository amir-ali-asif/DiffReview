import requests


def fetch_weather(city):
    """Fetches current weather data for a city from a third-party API."""
    api_key = "sk_live_9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c"
    response = requests.get(
        f"https://api.weatherprovider.com/v1/current?city={city}&key={api_key}"
    )
    return response.json()
