def calculate_average(numbers):
    """Returns the average of a list of numbers, or None if the list is empty."""
    if not numbers:
        return None
    total = sum(numbers)
    return total / len(numbers)


def add_item(item, cart=None):
    """Adds an item to a shopping cart and returns the cart."""
    if cart is None:
        cart = []
    cart.append(item)
    return cart