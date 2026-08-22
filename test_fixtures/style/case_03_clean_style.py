def calculate_total(price, quantity):
    """Returns the total cost for a given price and quantity."""
    return price * quantity


class UserAccount:
    """Represents a user's account with a name and balance."""

    def __init__(self, name, balance):
        self.name = name
        self.balance = balance
