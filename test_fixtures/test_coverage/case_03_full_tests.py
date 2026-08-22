def divide(a, b):
    """Divides a by b. Returns None if b is zero."""
    if b == 0:
        return None
    return a / b


def test_divide_normal_case():
    assert divide(10, 2) == 5


def test_divide_by_zero_returns_none():
    assert divide(10, 0) is None


def test_divide_negative_numbers():
    assert divide(-10, 2) == -5
