"""Weekday helpers."""
import datetime

NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def weekday_name(year, month, day):
    return NAMES[datetime.date(year, month, day).weekday()]


def is_weekend(year, month, day):
    return datetime.date(year, month, day).weekday() >= 5
