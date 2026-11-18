import unittest

from shopping_cart.cart import Cart
from shopping_cart.discounts import apply_coupon, percentage_off


class CartTests(unittest.TestCase):
    def test_subtotal_adds_up(self):
        cart = Cart()
        cart.add_item("pen", 2.5, 4)
        cart.add_item("book", 10)
        self.assertEqual(cart.subtotal(), 20.0)

    def test_adding_same_sku_accumulates(self):
        cart = Cart()
        cart.add_item("pen", 2.0)
        cart.add_item("pen", 2.0, 2)
        self.assertEqual(cart.subtotal(), 6.0)

    def test_remove_missing_item_raises(self):
        with self.assertRaises(KeyError):
            Cart().remove_item("nope")

    def test_total_without_coupon(self):
        cart = Cart()
        cart.add_item("lamp", 30)
        self.assertEqual(cart.total(), 30)


class DiscountTests(unittest.TestCase):
    def test_zero_percent_changes_nothing(self):
        self.assertEqual(percentage_off(100, 0), 100)

    def test_unknown_coupon_rejected(self):
        with self.assertRaises(ValueError):
            apply_coupon(100, "BOGUS")


if __name__ == "__main__":
    unittest.main()
