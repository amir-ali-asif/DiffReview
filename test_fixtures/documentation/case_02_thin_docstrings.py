def calculate_discount(price, percent):
    """price."""
    return price - (price * percent / 100)


def apply_tax(amount, rate):
    """Tax."""
    return amount + (amount * rate)
