"""Month and day calculations."""
from .leap import is_leap_year

_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def days_in_month(year, month):
    """Number of days in the given month (1-12) of the given year."""
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    if month == 2 and is_leap_year(year):
        return 29
    return _DAYS[month - 1]


def days_in_year(year):
    return sum(days_in_month(year, m) for m in range(1, 13))
