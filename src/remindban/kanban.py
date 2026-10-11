"""Kanban backends.

RemindBan talks to a board through ``KanbanBackend``. Vikunja is the only
adapter in v1. A new tool is a new class plus a branch in ``open_backend``.
"""

from __future__ import annotations

from typing import Protocol

from remindban.config import AppConfig
from remindban.errors import ConfigError
from remindban.models import BackendCapabilities, Card, ReminderDraft


class KanbanBackend(Protocol):
    """Operations every kanban tool must provide."""

    def capabilities(self) -> BackendCapabilities:
        """Whether the tool can show a derived Today bucket on its own."""

    def ensure_layout(self) -> None:
        """Create the project and the v1 buckets if they are missing."""

    def create_reminder(self, draft: ReminderDraft) -> Card:
        """File a new card in the intake bucket."""

    def list_cards(self) -> list[Card]:
        """Return every card on the project."""

    def move_card(self, card_id: str, bucket_title: str) -> None:
        """Move a card into the bucket with this title."""

    def update_labels(self, card: Card, labels: tuple[str, ...]) -> None:
        """Replace the card's labels with ``labels``."""


def open_backend(config: AppConfig) -> KanbanBackend:
    if config.provider != "vikunja":
        raise ConfigError(
            f"Kanban provider {config.provider!r} is not available. "
            "RemindBan v1 supports vikunja only."
        )
    from remindban.vikunja import VikunjaBackend

    return VikunjaBackend(
        project_title=config.project,
        settings=config.require_vikunja(),
        catalog=config.buckets,
    )
