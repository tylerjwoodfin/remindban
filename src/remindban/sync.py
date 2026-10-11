"""Decide which cards belong in the derived Today bucket.

The kanban tool is not asked to compute this. Callers that can derive the
column themselves should skip applying the plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from remindban.buckets import BucketCatalog
from remindban.models import Card

_DATE_IN_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}")
_EXACT_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Relabel:
    card: Card
    labels: tuple[str, ...]


@dataclass(frozen=True)
class Move:
    card: Card
    bucket: str


def belongs_in_today(labels: tuple[str, ...] | list[str], today: date) -> bool:
    """True when any label contains an ISO date on or before ``today``."""

    for label in labels:
        for match in _DATE_IN_TEXT.findall(label):
            try:
                found = date.fromisoformat(match)
            except ValueError:
                continue
            if found <= today:
                return True
    return False


def labels_for_due_date(card: Card) -> tuple[str, ...] | None:
    """Align the bare ``YYYY-MM-DD`` label with the due date.

    Other labels stay. Returns None when the card has no due date, is done,
    or the date label is already correct. A repeating task's due date moves
    when Vikunja reopens it; this is what keeps Today from using the old date.
    """

    if card.done or card.due is None:
        return None
    wanted = card.due.isoformat()
    exact = [label for label in card.labels if _EXACT_DATE.fullmatch(label)]
    if exact == [wanted]:
        return None
    others = [label for label in card.labels if not _EXACT_DATE.fullmatch(label)]
    return tuple(others + [wanted])


def plan_sync(
    cards: list[Card],
    catalog: BucketCatalog,
    today: date,
) -> list[Relabel | Move]:
    """Plan label repairs and moves. In Progress and Done stay where they are."""

    actions: list[Relabel | Move] = []
    derived = catalog.derived.title
    intake = catalog.intake.title
    sticky = catalog.sticky_titles()
    for card in cards:
        if card.done:
            continue
        updated = labels_for_due_date(card)
        labels = updated if updated is not None else card.labels
        if updated is not None:
            actions.append(Relabel(card, updated))
        current = card.bucket.casefold()
        if current in sticky:
            continue
        in_today = current == derived.casefold()
        belongs = belongs_in_today(labels, today)
        if belongs and not in_today:
            actions.append(Move(card, derived))
        elif in_today and not belongs:
            actions.append(Move(card, intake))
    return actions
