import unittest

from text_utils import count_words, slugify, truncate


class TextUtilsTests(unittest.TestCase):
    def test_count_words_simple(self):
        self.assertEqual(count_words("the quick brown fox"), 4)

    def test_count_words_empty(self):
        self.assertEqual(count_words(""), 0)

    def test_slugify(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_truncate_short_text_unchanged(self):
        self.assertEqual(truncate("hi", 10), "hi")

    def test_truncate_long_text(self):
        self.assertEqual(truncate("abcdefghij", 8), "abcde...")


if __name__ == "__main__":
    unittest.main()
