from datetime import date

import pytest

from remindban.errors import ParseError
from remindban.models import RepeatMode
from remindban.when import apply_starts_on, parse_when

TODAY = date(2026, 10, 10)  # Saturday


def test_relative_and_named_dates():
    assert parse_when("tomorrow", today=TODAY).due == date(2026, 10, 11)
    assert parse_when("friday", today=TODAY).due == date(2026, 10, 16)
    assert parse_when("saturday", today=TODAY).due == TODAY
    assert parse_when("Oct 12", today=TODAY).due == date(2026, 10, 12)
    assert parse_when("January 2", today=TODAY).due == date(2027, 1, 2)
    assert parse_when("2026-10-15", today=TODAY).due == date(2026, 10, 15)
    assert parse_when("in 3 weeks", today=TODAY).due == date(2026, 10, 31)
    assert parse_when("every december 1", today=TODAY).due == date(2026, 12, 1)


def test_repeat_modes_match_vikunja_fields():
    weekly = parse_when("every 2 weeks", today=TODAY)
    assert weekly.repeat.to_vikunja() == (2 * 7 * 86400, 0)
    assert weekly.due == TODAY

    tuesday = parse_when("every 2 tuesdays", today=TODAY)
    assert tuesday.due == date(2026, 10, 13)
    assert tuesday.repeat.to_vikunja() == (2 * 7 * 86400, 0)

    monthly = parse_when("every month", today=TODAY)
    assert monthly.repeat.mode is RepeatMode.MONTHLY
    assert monthly.repeat.to_vikunja() == (0, 1)

    current = parse_when("every 3 days from completion", today=TODAY)
    assert current.repeat.mode is RepeatMode.FROM_CURRENT_DATE
    assert current.repeat.to_vikunja() == (3 * 86400, 2)

    yearly = parse_when("every year", today=TODAY)
    assert yearly.repeat.to_vikunja() == (365 * 86400, 0)
    assert "365 days" in yearly.warning


def test_aliases_and_starts_on():
    parsed = parse_when("biweekly", today=TODAY)
    moved = apply_starts_on(parsed, "2026-11-02", today=TODAY)
    assert moved.due == date(2026, 11, 2)
    assert moved.repeat.to_vikunja() == parsed.repeat.to_vikunja()


def test_unsupported_recurrence_is_explicit():
    with pytest.raises(ParseError, match="every month"):
        parse_when("every 2 months", today=TODAY)
    with pytest.raises(ParseError, match="cannot store"):
        parse_when("first tuesday of the month", today=TODAY)
    with pytest.raises(ParseError, match="from completion"):
        parse_when("tomorrow from completion", today=TODAY)
    with pytest.raises(ParseError, match="not a real date"):
        parse_when("2026-02-31", today=TODAY)


def test_empty_when():
    with pytest.raises(ParseError, match="when this reminder"):
        parse_when("   ", today=TODAY)
