"""The shopping cart."""
from .discounts import apply_coupon
from .formatting import format_money


class Cart:
    def __init__(self):
        self._items = {}  # sku -> [unit_price, quantity]
        self.coupon = None

    def add_item(self, sku, price, quantity=1):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price < 0:
            raise ValueError("price cannot be negative")
        if sku in self._items:
            self._items[sku][1] += quantity
        else:
            self._items[sku] = [price, quantity]

    def remove_item(self, sku):
        if sku not in self._items:
            raise KeyError(sku)
        del self._items[sku]

    def subtotal(self):
        return sum(price * qty for price, qty in self._items.values())

    def set_coupon(self, code):
        """Remember a coupon code to be applied by total()."""
        self.coupon = code

    def total(self):
        amount = self.subtotal()
        if self.coupon:
            amount = apply_coupon(amount, self.coupon)
        return round(amount, 2)

    def summary(self):
        return f"{len(self._items)} item(s), total {format_money(self.total())}"
