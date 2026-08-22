import os
import sqlite3


def get_user_by_name(db_path, username):
    """Fetches a user record by username using a parameterized query."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cursor.fetchone()


def fetch_weather(city):
    """Fetches current weather data using an API key loaded from the environment."""
    api_key = os.environ["WEATHER_API_KEY"]
    return {"city": city, "api_key_loaded": bool(api_key)}
