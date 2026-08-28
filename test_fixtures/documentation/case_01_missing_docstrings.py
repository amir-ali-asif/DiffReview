def calculate_discount(price, percent):
    return price - (price * percent / 100)


class ShoppingCart:
    def __init__(self, items):
        self.items = items

    def total(self):
        return sum(item.price for item in self.items)
