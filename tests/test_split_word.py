import pytest

from bionic_epub.converter import BionicConverter


def make_converter(**overrides):
    prefs = {
        'boldness_ratio': 50,
        'min_word_length': 1,
        'skip_short_words': False,
    }
    prefs.update(overrides)
    return BionicConverter(prefs)


@pytest.mark.parametrize(
    'word,expected',
    [
        ('a', ('a', '')),
        ('the', ('t', 'he')),
        ('word', ('wo', 'rd')),
        ('quick', ('qu', 'ick')),
        ('reading', ('read', 'ing')),
    ],
)
def test_split_word_default_ratio(word, expected):
    assert make_converter()._split_word(word) == expected


@pytest.mark.parametrize(
    'ratio,word,expected',
    [
        (25, 'word', ('w', 'ord')),
        (50, 'word', ('wo', 'rd')),
        (75, 'word', ('wor', 'd')),
    ],
)
def test_split_word_respects_boldness_ratio(ratio, word, expected):
    assert make_converter(boldness_ratio=ratio)._split_word(word) == expected


def test_split_word_never_bolds_entire_long_word():
    bold, rest = make_converter(boldness_ratio=75)._split_word('abcd')
    assert rest
    assert bold + rest == 'abcd'


def test_skip_short_words_leaves_one_and_two_letter_words():
    converter = make_converter(skip_short_words=True)
    assert converter._split_word('a') == (None, None)
    assert converter._split_word('an') == (None, None)
    assert converter._split_word('the') == ('t', 'he')


def test_min_word_length_skips_shorter_words():
    converter = make_converter(min_word_length=4)
    assert converter._split_word('the') == (None, None)
    assert converter._split_word('word') == ('wo', 'rd')
