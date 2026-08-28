def has_duplicates(items):
    """Checks whether a list contains any duplicate values."""
    return len(items) != len(set(items))


def build_report(rows):
    """Builds a text report by joining a line for each row."""
    lines = [f"{row['name']}: {row['value']}" for row in rows]
    return "\n".join(lines) + "\n"
