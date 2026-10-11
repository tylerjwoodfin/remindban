"""Turn the add-reminder form into a card, and describe it before it is saved."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from remindban.errors import ParseError
from remindban.models import ReminderDraft, RepeatSpec
from remindban.when import ParsedWhen, parse_when

REPEAT_CHOICES: tuple[tuple[str, str], ...] = (
    ("auto", "Match the When phrase"),
    ("none", "Does not repeat"),
    ("interval", "On an interval"),
    ("monthly", "Monthly, on this day of the month"),
    ("from_completion", "From the day you complete it"),
)
UNITS: tuple[str, ...] = ("days", "weeks", "years")


@dataclass
class ComposerState:
    title: str = ""
    when_text: str = ""
    notes: str = ""
    labels: str = ""
    repeat_choice: str = "auto"
    every: str = "1"
    unit: str = "weeks"


def resolve_composer(state: ComposerState, *, today: date | None = None) -> ReminderDraft:
    """Validate the form. Raises ``ParseError`` with a message for the preview."""

    title = " ".join(state.title.split())
    if not title:
        raise ParseError("A reminder needs a title.")
    anchor = today or date.today()
    parsed = parse_when(state.when_text, today=anchor)
    repeat = _repeat_choice(state, parsed)
    labels = tuple(part.strip() for part in state.labels.split(",") if part.strip())
    return ReminderDraft(
        title=title,
        due=parsed.due,
        repeat=repeat,
        notes=state.notes.strip(),
        labels=labels,
    )


def preview_message(state: ComposerState, *, today: date | None = None, intake: str = "Backlog") -> str:
    """Plain-text preview, including the reason a card cannot be saved yet."""

    anchor = today or date.today()
    try:
        title = " ".join(state.title.split())
        if not title:
            raise ParseError("A reminder needs a title.")
        parsed = parse_when(state.when_text, today=anchor)
        draft = resolve_composer(state, today=anchor)
    except ParseError as exc:
        return str(exc)

    lines = [
        f"Bucket     {intake}",
        f"Due        {draft.due.strftime('%A, %d %b %Y')}",
        f"Date label {draft.date_label}",
        f"Repeat     {draft.repeat.describe()}",
    ]
    if draft.due < anchor:
        lines.append("This date is already past, so the next sync will move the card to Today.")
    elif state.repeat_choice == "auto" and parsed.warning:
        lines.append(parsed.warning)
    return "\n".join(lines)


def _repeat_choice(state: ComposerState, parsed: ParsedWhen) -> RepeatSpec:
    choice = state.repeat_choice
    if choice == "auto":
        return parsed.repeat
    if choice == "none":
        return RepeatSpec.none()
    if choice == "monthly":
        return RepeatSpec.monthly()
    every = _positive_int(state.every)
    unit = state.unit if state.unit in UNITS else "weeks"
    if choice == "interval":
        return RepeatSpec.interval(every, unit)
    if choice == "from_completion":
        return RepeatSpec.from_current_date(every, unit)
    raise ParseError(f"Unknown repeat choice {choice!r}.")


def _positive_int(value: str) -> int:
    text = value.strip()
    if not text.isdigit() or int(text) < 1:
        raise ParseError("Every needs a whole number, 1 or more.")
    return int(text)
