"""Errors a person can act on.

Library code raises these instead of letting raw filesystem, YAML, or HTTP
failures reach the terminal. The CLI prints ``remindban: <message>``.
"""

from __future__ import annotations


class RemindBanError(Exception):
    """Base for expected failures."""


class ConfigError(RemindBanError):
    """The config file or its credentials are missing or invalid."""


class ParseError(RemindBanError):
    """A reminder date or repeat phrase could not be understood."""


class KanbanError(RemindBanError):
    """The kanban provider rejected a request or could not be reached."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ScheduleError(RemindBanError):
    """A cron table or systemd timer could not be installed."""
