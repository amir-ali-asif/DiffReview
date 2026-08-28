def build_report(rows):
    """Builds a text report by concatenating a line for each row."""
    report = ""
    for row in rows:
        report += f"{row['name']}: {row['value']}\n"
    return report
