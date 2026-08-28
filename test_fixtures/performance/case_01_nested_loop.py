def has_duplicates(items):
    """Checks whether a list contains any duplicate values."""
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j]:
                return True
    return False
