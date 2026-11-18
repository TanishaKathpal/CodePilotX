import unittest

from pagination import has_next_page, paginate, total_pages


class PaginatorTests(unittest.TestCase):
    def test_total_pages_exact(self):
        self.assertEqual(total_pages(10, 5), 2)

    def test_total_pages_rounds_up(self):
        self.assertEqual(total_pages(11, 5), 3)

    def test_total_pages_empty(self):
        self.assertEqual(total_pages(0, 5), 0)

    def test_invalid_per_page(self):
        with self.assertRaises(ValueError):
            paginate([1, 2, 3], 1, 0)

    def test_page_far_past_the_end_is_empty(self):
        self.assertEqual(paginate([1, 2, 3], 50, 2), [])

    def test_has_next_page(self):
        self.assertTrue(has_next_page(10, 1, 5))
        self.assertFalse(has_next_page(10, 2, 5))


if __name__ == "__main__":
    unittest.main()
