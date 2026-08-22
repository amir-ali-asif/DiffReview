import sqlite3


def get_user_by_name(db_path, username):
    """Fetches a user record by username."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchone()
