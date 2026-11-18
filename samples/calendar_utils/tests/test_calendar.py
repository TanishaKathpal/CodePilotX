import unittest

from calendar_utils import days_in_month, is_leap_year


class CalendarTests(unittest.TestCase):
    def test_ordinary_leap_year(self):
        self.assertTrue(is_leap_year(2024))

    def test_ordinary_common_year(self):
        self.assertFalse(is_leap_year(2023))

    def test_century_is_not_leap(self):
        self.assertFalse(is_leap_year(1900))

    def test_days_in_month(self):
        self.assertEqual(days_in_month(2023, 1), 31)
        self.assertEqual(days_in_month(2023, 2), 28)
        self.assertEqual(days_in_month(2024, 2), 29)

    def test_bad_month(self):
        with self.assertRaises(ValueError):
            days_in_month(2024, 13)


if __name__ == "__main__":
    unittest.main()
