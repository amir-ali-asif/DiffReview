def add_item(item, cart=[]):
    """Adds an item to a shopping cart and returns the cart."""
    cart.append(item)
    return cart


def get_user_role(username, roles={}):
    """Looks up a user's role, defaulting to 'guest' if not found."""
    if username not in roles:
        roles[username] = "guest"
    return roles[username]
