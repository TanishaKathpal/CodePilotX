"""Coupon and discount helpers."""

# coupon code -> percent off
COUPONS = {
    "SAVE10": 10,
    "SAVE25": 25,
    "WELCOME5": 5,
}


def percentage_off(amount, percent):
    """Return `amount` after taking `percent` percent off."""
    return amount - amount * percent


def apply_coupon(amount, code):
    """Apply a coupon code to an amount. Unknown codes raise ValueError."""
    code = code.strip().upper()
    if code not in COUPONS:
        raise ValueError(f"Unknown coupon: {code}")
    return percentage_off(amount, COUPONS[code])
