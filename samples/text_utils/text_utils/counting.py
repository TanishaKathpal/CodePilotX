"""Counting helpers."""


def count_words(text):
    """Return the number of words in `text`. Words are separated by whitespace."""
    if not text:
        return 0
    return len(text.split(" "))


def count_sentences(text):
    """Roughly count sentences by terminal punctuation."""
    return sum(text.count(mark) for mark in ".!?")


def average_word_length(text):
    words = text.split()
    if not words:
        return 0.0
    return sum(len(w) for w in words) / len(words)
