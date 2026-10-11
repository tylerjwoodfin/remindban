"""Reminders and cards, with no knowledge of a particular kanban vendor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class RepeatMode(Enum):
    """How a finished card schedules its next due date.

    These names match the Vikunja user docs. ``to_vikunja`` maps them onto the
    v2.6 fields ``repeat_after`` (seconds) and ``repeat_mode`` (0, 1, or 2).
    """

    NONE = "none"
    INTERVAL = "interval"
    MONTHLY = "monthly"
    FROM_CURRENT_DATE = "from_current_date"


_UNIT_SECONDS = {
    "days": 86_400,
    "weeks": 7 * 86_400,
    "years": 365 * 86_400,
}


@dataclass(frozen=True)
class RepeatSpec:
    """A recurrence RemindBan can store on a card."""

    mode: RepeatMode = RepeatMode.NONE
    every: int = 1
    unit: str = "days"

    def __post_init__(self) -> None:
        if self.every < 1:
            raise ValueError("Repeat interval must be at least 1.")
        if self.unit not in _UNIT_SECONDS:
            raise ValueError(f"Unknown repeat unit {self.unit!r}.")
        if self.mode is RepeatMode.MONTHLY and (self.every != 1 or self.unit != "days"):
            raise ValueError("Monthly repeat uses the due date's day of the month.")

    @classmethod
    def none(cls) -> RepeatSpec:
        return cls()

    @classmethod
    def interval(cls, every: int, unit: str) -> RepeatSpec:
        return cls(RepeatMode.INTERVAL, every, unit)

    @classmethod
    def monthly(cls) -> RepeatSpec:
        return cls(RepeatMode.MONTHLY, 1, "days")

    @classmethod
    def from_current_date(cls, every: int, unit: str) -> RepeatSpec:
        return cls(RepeatMode.FROM_CURRENT_DATE, every, unit)

    def to_vikunja(self) -> tuple[int, int]:
        """Return ``(repeat_after, repeat_mode)`` for Vikunja 2.6."""

        if self.mode is RepeatMode.NONE:
            return 0, 0
        if self.mode is RepeatMode.MONTHLY:
            return 0, 1
        seconds = _UNIT_SECONDS[self.unit] * self.every
        mode = 2 if self.mode is RepeatMode.FROM_CURRENT_DATE else 0
        return seconds, mode

    def describe(self) -> str:
        if self.mode is RepeatMode.NONE:
            return "Does not repeat"
        if self.mode is RepeatMode.MONTHLY:
            return "Monthly, on this day of the month"
        count = f"{self.every} " if self.every != 1 else ""
        unit = self.unit if self.every != 1 else self.unit[:-1]
        if self.mode is RepeatMode.FROM_CURRENT_DATE:
            return f"Every {count}{unit} after you complete it"
        if self.unit == "years":
            return f"Every {count}{unit} (stored as {self.every * 365} days)"
        return f"Every {count}{unit}"


@dataclass(frozen=True)
class ReminderDraft:
    """A reminder ready to become a backlog card."""

    title: str
    due: date
    repeat: RepeatSpec = field(default_factory=RepeatSpec.none)
    notes: str = ""
    labels: tuple[str, ...] = ()

    @property
    def date_label(self) -> str:
        return self.due.isoformat()


@dataclass(frozen=True)
class Card:
    """A task as RemindBan sees it after reading the board."""

    id: str
    identifier: str
    title: str
    notes: str
    due: date | None
    labels: tuple[str, ...]
    bucket: str
    done: bool
    repeat_after: int = 0
    repeat_mode: int = 0
    url: str = ""


@dataclass(frozen=True)
class BackendCapabilities:
    """What the connected kanban tool can do without RemindBan's help."""

    derived_buckets: bool
    reason: str
