from datetime import date

import pytest

from hrdpa_pipeline.core import choose_band, date_range, default_start


def test_date_range_is_inclusive():
    assert date_range(date(2026, 5, 1), date(2026, 5, 3)) == [
        date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)
    ]


def test_default_start_uses_current_year():
    assert default_start(date(2026, 8, 13)) == date(2026, 5, 1)


def test_band_must_be_unambiguous():
    assert choose_band(["precip"], None) == "precip"
    with pytest.raises(ValueError):
        choose_band(["a", "b"], None)

