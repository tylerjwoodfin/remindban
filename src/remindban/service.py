"""Board operations shared by the CLI, independent of how the terminal looks."""

from __future__ import annotations

import sys
from datetime import date

from remindban.config import AppConfig
from remindban.kanban import KanbanBackend
from remindban.models import Card, ReminderDraft
from remindban.sync import Move, Relabel, belongs_in_today, labels_for_due_date, plan_sync


class Board:
    def __init__(self, config: AppConfig, backend: KanbanBackend) -> None:
        self.config = config
        self.backend = backend

    def add(self, draft: ReminderDraft) -> Card:
        return self.backend.create_reminder(draft)

    def cards(self) -> list[Card]:
        return self.backend.list_cards()

    def prepare(self) -> None:
        self.backend.ensure_layout()

    def sync(self, today: date, *, dry_run: bool) -> list[Relabel | Move]:
        actions = plan_sync(self.cards(), self.config.buckets, today)
        if dry_run:
            return actions
        for action in actions:
            if isinstance(action, Relabel):
                self.backend.update_labels(action.card, action.labels)
            else:
                self.backend.move_card(action.card.id, action.bucket)
        return actions


def effective_labels(card: Card) -> tuple[str, ...]:
    updated = labels_for_due_date(card)
    return updated if updated is not None else card.labels


def today_cards(cards: list[Card], today: date) -> list[Card]:
    return [
        card
        for card in cards
        if not card.done and belongs_in_today(effective_labels(card), today)
    ]


def describe_stored_repeat(repeat_after: int, repeat_mode: int) -> str:
    if repeat_mode == 1:
        return "monthly"
    if repeat_after <= 0:
        return ""
    year = 365 * 86_400
    week = 7 * 86_400
    day = 86_400
    if repeat_after % year == 0:
        count, unit = repeat_after // year, "year"
    elif repeat_after % week == 0:
        count, unit = repeat_after // week, "week"
    elif repeat_after % day == 0:
        count, unit = repeat_after // day, "day"
    else:
        count, unit = repeat_after, "second"
    base = f"every {unit}" if count == 1 else f"every {count} {unit}s"
    if repeat_mode == 2:
        base += " from completion"
    if unit == "year":
        base += " (365-day interval)"
    return base


def format_card_line(card: Card) -> str:
    due = card.due.isoformat() if card.due else "no due date"
    repeat = describe_stored_repeat(card.repeat_after, card.repeat_mode)
    suffix = f"  {repeat}" if repeat else ""
    return f"  {card.identifier:<14} {card.title}  due {due}{suffix}"


def format_board(cards: list[Card], config: AppConfig) -> str:
    groups = {spec.title: [] for spec in config.buckets.specs}
    other: list[Card] = []
    for card in cards:
        spec = config.buckets.matching(card.bucket)
        if spec is None:
            other.append(card)
        else:
            groups[spec.title].append(card)
    lines: list[str] = []
    for title, rows in groups.items():
        lines.append(title)
        lines.extend(format_card_line(card) for card in rows)
        if not rows:
            lines.append("  (empty)")
        lines.append("")
    if other:
        lines.append("Other")
        lines.extend(format_card_line(card) for card in other)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_sync(actions: list[Relabel | Move], *, dry_run: bool) -> str:
    if not actions:
        return "Today is already up to date.\n"
    lines: list[str] = []
    for action in actions:
        if isinstance(action, Relabel):
            verb = "Would update the date label on" if dry_run else "Updated the date label on"
            lines.append(f"{verb} {action.card.identifier} ({action.card.title})")
        else:
            verb = "Would move" if dry_run else "Moved"
            lines.append(f"{verb} {action.card.identifier} ({action.card.title}) to {action.bucket}")
    return "\n".join(lines) + "\n"


def format_saved(card: Card) -> str:
    due = card.due.isoformat() if card.due else "no due date"
    link = f"\n{_terminal_link(card.url)}" if card.url else ""
    return f"Saved {card.identifier} to {card.bucket} · due {due}{link}\n"


def _terminal_link(url: str) -> str:
    if not sys.stdout.isatty():
        return url
    return f"\033]8;;{url}\033\\{url}\033]8;;\033\\"
