def process_order(order):
    """Processes an order and returns its status."""
    if order is not None:
        if order.get("items"):
            if order.get("payment_confirmed"):
                if order.get("shipping_address"):
                    if order.get("stock_available"):
                        return "ready_to_ship"
                    else:
                        return "backordered"
                else:
                    return "missing_address"
            else:
                return "awaiting_payment"
        else:
            return "empty_order"
    else:
        return "invalid_order"
