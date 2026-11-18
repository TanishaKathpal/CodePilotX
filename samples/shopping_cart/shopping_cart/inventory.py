"""Stock tracking for the shop (not used by Cart directly)."""


class Inventory:
    def __init__(self):
        self._stock = {}

    def restock(self, sku, quantity):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self._stock[sku] = self._stock.get(sku, 0) + quantity

    def in_stock(self, sku, quantity=1):
        return self._stock.get(sku, 0) >= quantity

    def reserve(self, sku, quantity):
        if not self.in_stock(sku, quantity):
            raise ValueError(f"Not enough stock for {sku}")
        self._stock[sku] -= quantity
