"""Leap year logic."""


def is_leap_year(year):
    """Return True if `year` is a leap year in the Gregorian calendar."""
    return year % 4 == 0 and year % 100 != 0
