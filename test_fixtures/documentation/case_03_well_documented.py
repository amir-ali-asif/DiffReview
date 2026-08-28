def calculate_discount(price, percent):
    """
    Calculates the discounted price.

    Args:
        price (float): The original price.
        percent (float): The discount percentage (0-100).

    Returns:
        float: The price after applying the discount.
    """
    return price - (price * percent / 100)


class ShoppingCart:
    """Represents a shopping cart holding a list of items."""

    def __init__(self, items):
        self.items = items

    def total(self):
        """Returns the total price of all items in the cart."""
        return sum(item.price for item in self.items)
