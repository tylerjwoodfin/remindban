"""Natural-language due dates and Vikunja repeat rules."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from remindban.errors import ParseError
from remindban.models import RepeatMode, RepeatSpec

_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_UNITS = {
    "day": "days",
    "days": "days",
    "week": "weeks",
    "weeks": "weeks",
    "month": "months",
    "months": "months",
    "year": "years",
    "years": "years",
}

_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WEEKDAY_PATTERN = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))


@dataclass(frozen=True)
class ParsedWhen:
    """A due date plus the repeat rule parsed from the same phrase."""

    due: date
    repeat: RepeatSpec
    warning: str = ""


def parse_when(text: str, *, today: date | None = None) -> ParsedWhen:
    """Parse a phrase such as ``tomorrow`` or ``every 2 weeks``."""

    raw = " ".join(text.strip().split())
    if not raw:
        raise ParseError("Tell RemindBan when this reminder is due.")
    anchor = today or date.today()
    lowered = raw.casefold()
    from_current = False
    for suffix in (
        " from completion",
        " from current date",
        " from the current date",
    ):
        if lowered.endswith(suffix):
            from_current = True
            lowered = lowered[: -len(suffix)].strip()
            break

    lowered = _aliases(lowered)
    if re.search(r"\b(first|second|third|fourth|last)\b.+\bof\b", lowered):
        raise ParseError(
            f"{raw!r} needs a recurrence Vikunja 2.6 cannot store. "
            "Use a weekday interval such as 'every 2 tuesdays', or 'every month'."
        )

    parsed = _parse_body(lowered, anchor, raw)
    if from_current:
        if parsed.repeat.mode is RepeatMode.MONTHLY:
            raise ParseError(
                "Vikunja cannot combine monthly repeat with 'from completion'. "
                "Use 'every month', or an interval such as 'every 4 weeks from completion'."
            )
        if parsed.repeat.mode is RepeatMode.NONE:
            raise ParseError(
                "Add an interval before 'from completion', for example 'every 2 weeks from completion'."
            )
        parsed = replace(
            parsed,
            repeat=RepeatSpec.from_current_date(parsed.repeat.every, parsed.repeat.unit),
        )
    return parsed


def apply_starts_on(parsed: ParsedWhen, starts_on: str, *, today: date | None = None) -> ParsedWhen:
    """Keep the repeat rule and replace the first due date."""

    text = starts_on.strip()
    if not text:
        return parsed
    if text.casefold().startswith("every"):
        raise ParseError("--starts-on needs a single date, not a repeat phrase.")
    due = _parse_body(text.casefold(), today or date.today(), text).due
    return replace(parsed, due=due, repeat=parsed.repeat)


def _aliases(text: str) -> str:
    replacements = {
        "daily": "every day",
        "weekly": "every week",
        "biweekly": "every 2 weeks",
        "monthly": "every month",
        "yearly": "every year",
        "annually": "every year",
        "every other day": "every 2 days",
        "every other week": "every 2 weeks",
    }
    return replacements.get(text, text)


def _parse_body(text: str, today: date, original: str) -> ParsedWhen:
    if text in {"today", "tonight"}:
        return ParsedWhen(today, RepeatSpec.none())
    if text == "tomorrow":
        return ParsedWhen(today + timedelta(days=1), RepeatSpec.none())

    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return ParsedWhen(_safe_date(*_ints(iso.groups()), original=original), RepeatSpec.none())

    mdy = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if mdy:
        month, day, year = _ints(mdy.groups())
        return ParsedWhen(_safe_date(year, month, day, original=original), RepeatSpec.none())

    md = re.fullmatch(r"(\d{1,2})/(\d{1,2})", text)
    if md:
        month, day = _ints(md.groups())
        return ParsedWhen(_next_month_day(today, month, day), RepeatSpec.none())

    relative = re.fullmatch(r"(?:in\s+)?(\d+)\s+(day|days|week|weeks|month|months|year|years)(?:\s+from now)?", text)
    if relative and not text.startswith("every"):
        count = int(relative.group(1))
        unit = _UNITS[relative.group(2)]
        return ParsedWhen(_add(today, count, unit), RepeatSpec.none())

    every_named = re.fullmatch(
        rf"every\s+(?:(\d+)\s+)?({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?",
        text,
    )
    if every_named:
        count = int(every_named.group(1) or "1")
        month = _MONTHS[every_named.group(2)]
        day = int(every_named.group(3))
        if count != 1:
            raise ParseError(
                "Vikunja's monthly mode repeats every month, not every "
                f"{count} months. Use 'every {count * 4} weeks' or 'every year'."
            )
        due = _next_month_day(today, month, day)
        return ParsedWhen(
            due,
            RepeatSpec.interval(1, "years"),
            warning="Vikunja stores a yearly repeat as 365 days, so a leap year can shift the next date.",
        )

    every_dow = re.fullmatch(
        rf"every\s+(?:(\d+)\s+)?({_WEEKDAY_PATTERN})s?",
        text,
    )
    if every_dow:
        count = int(every_dow.group(1) or "1")
        weekday = _WEEKDAYS[every_dow.group(2)]
        return ParsedWhen(_next_weekday(today, weekday), RepeatSpec.interval(count, "weeks"))

    every = re.fullmatch(
        r"every\s+(?:(\d+)\s+)?(day|days|week|weeks|month|months|year|years)",
        text,
    )
    if every:
        count = int(every.group(1) or "1")
        unit = _UNITS[every.group(2)]
        return _every(today, count, unit)

    named = re.fullmatch(
        rf"({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?",
        text,
    )
    if named:
        month = _MONTHS[named.group(1)]
        day = int(named.group(2))
        if named.group(3):
            due = _safe_date(int(named.group(3)), month, day, original=original)
        else:
            due = _next_month_day(today, month, day)
        return ParsedWhen(due, RepeatSpec.none())

    if text in _WEEKDAYS:
        return ParsedWhen(_next_weekday(today, _WEEKDAYS[text]), RepeatSpec.none())

    raise ParseError(
        f"Could not read {original!r}. Try 'tomorrow', 'friday', '2026-10-12', "
        "'every 2 weeks', or 'every month'."
    )


def _every(today: date, count: int, unit: str) -> ParsedWhen:
    if unit == "months":
        if count != 1:
            raise ParseError(
                f"Vikunja cannot repeat every {count} months. "
                "Use 'every month' for the same day each month, or an interval in weeks."
            )
        return ParsedWhen(today, RepeatSpec.monthly())
    if unit == "years" and count != 1:
        return ParsedWhen(
            today,
            RepeatSpec.interval(count, "years"),
            warning="Vikunja stores a yearly repeat as 365 days, so a leap year can shift the next date.",
        )
    if unit == "years":
        return ParsedWhen(
            today,
            RepeatSpec.interval(1, "years"),
            warning="Vikunja stores a yearly repeat as 365 days, so a leap year can shift the next date.",
        )
    return ParsedWhen(today, RepeatSpec.interval(count, unit))


def _add(today: date, count: int, unit: str) -> date:
    if unit == "days":
        return today + timedelta(days=count)
    if unit == "weeks":
        return today + timedelta(weeks=count)
    if unit == "months":
        return today + relativedelta(months=count)
    return today + relativedelta(years=count)


def _next_weekday(today: date, weekday: int) -> date:
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _next_month_day(today: date, month: int, day: int) -> date:
    year = today.year
    due = _safe_date(year, month, day, original=f"{month}/{day}")
    if due < today:
        due = _safe_date(year + 1, month, day, original=f"{month}/{day}")
    return due


def _safe_date(year: int, month: int, day: int, *, original: str) -> date:
    if month < 1 or month > 12:
        raise ParseError(f"{original!r} is not a real date.")
    last = calendar.monthrange(year, month)[1]
    if day < 1 or day > last:
        raise ParseError(f"{original!r} is not a real date.")
    return date(year, month, day)


def _ints(groups: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(int(value) for value in groups)
