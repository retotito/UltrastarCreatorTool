import pytest

from services.http_range import RangeNotSatisfiable, parse_range


@pytest.mark.parametrize('header, expected', [
    (None, None),
    ('', None),
    ('bytes=0-99', (0, 99)),
    ('bytes=0-1', (0, 1)),
    ('bytes=100-', (100, 999)),
    ('bytes=0-', (0, 999)),
    ('bytes=900-5000', (900, 999)),          # end past the file: cut
    ('bytes=-128', (872, 999)),              # the last 128 bytes (GStreamer looks for MP3 tags there)
    ('bytes=-5000', (0, 999)),
    ('bytes=0-9, 20-29', (0, 9)),            # several ranges: the first
    (' Bytes = 5-6', (5, 6)),
    ('items=0-9', None),                     # not bytes: the whole file
    ('bytes=abc', None),
    ('bytes=9-3', None),
])
def test_parse_range(header, expected):
    assert parse_range(header, 1000) == expected


@pytest.mark.parametrize('header, size', [
    ('bytes=1000-', 1000),
    ('bytes=2000-3000', 1000),
    ('bytes=-0', 1000),
    ('bytes=-10', 0),
])
def test_unsatisfiable(header, size):
    with pytest.raises(RangeNotSatisfiable):
        parse_range(header, size)
