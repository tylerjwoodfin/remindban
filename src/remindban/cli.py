"""Terminal entrypoint.

Flags match RemindMail closely (``--title``, ``--when``, ``--edit``, ``--save``).
Subcommands cover the board: ``list``, ``sync``, ``today``, ``init``, and
``install-sync``.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from remindban import __version__
from remindban.compose import ComposerState, resolve_composer
from remindban.config import ensure_config_file, load_config, resolve_config_path
from remindban.errors import ConfigError, ParseError, RemindBanError
from remindban.kanban import open_backend
from remindban.models import BackendCapabilities
from remindban.schedule import install_cron, install_systemd
from remindban.service import (
    Board,
    effective_labels,
    format_board,
    format_card_line,
    format_saved,
    format_sync,
    today_cards,
)
from remindban.tui import run_composer
from remindban.when import ParsedWhen, apply_starts_on

COMMANDS = ("add", "edit", "list", "sync", "today", "find", "init", "install-sync")


def execute(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print()
        return 130
    except RemindBanError as exc:
        print(f"remindban: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if getattr(args, "debug", False):
            raise
        print(f"remindban: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(execute(argv))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remindban",
        description="Save reminders onto a kanban board. Vikunja is the board in v1.",
    )
    parser.add_argument("command", nargs="?", default="add", help=" ".join(COMMANDS))
    parser.add_argument("rest", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--title", nargs="+", help="reminder title")
    parser.add_argument("--when", help="when it is due, in plain language")
    parser.add_argument("--notes", help="description stored on the card")
    parser.add_argument("--labels", help="comma-separated extra labels")
    parser.add_argument("--starts-on", help="first due date, keeping the repeat from --when")
    parser.add_argument("--save", action="store_true", help="save without the confirmation form")
    parser.add_argument("--edit", action="store_true", help="open the config file")
    parser.add_argument("--list", action="store_true", help="list cards by bucket")
    parser.add_argument("--sync", action="store_true", help="move due cards into Today")
    parser.add_argument("--today", action="store_true", help="show cards whose date label is due")
    parser.add_argument("--find", help="search titles, notes, labels, and dates")
    parser.add_argument("--init", action="store_true", help="create the Remindban project and buckets")
    parser.add_argument("--install-sync", action="store_true", help="schedule sync at sync.time")
    parser.add_argument("--systemd", action="store_true", help="install a systemd user timer")
    parser.add_argument("--dry-run", action="store_true", help="with sync, print moves without writing")
    parser.add_argument("--file", help="path to the config file")
    parser.add_argument("--debug", action="store_true", help="show unexpected tracebacks")
    parser.add_argument("--version", action="version", version=f"remindban {__version__}")
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    command = _command(args)
    if command == "edit":
        _edit(resolve_config_path(args.file))
        return 0
    config = load_config(args.file)
    config.require_vikunja()
    if command == "add":
        return _add(args, config)
    board = Board(config, open_backend(config))
    if command == "init":
        board.prepare()
        names = ", ".join(spec.title for spec in config.buckets.specs)
        print(f"Project {config.project} is ready.")
        print(f"Buckets: {names}.")
        _explain_today(board.backend.capabilities(), config.sync.at)
        return 0
    if command == "list":
        print(format_board(board.cards(), config), end="")
        return 0
    if command == "today":
        _print_today(board, date.today())
        return 0
    if command == "find":
        _print_find(board, _query(args))
        return 0
    if command == "sync":
        _run_sync(board, dry_run=args.dry_run)
        return 0
    if command == "install-sync":
        _install(config, board.backend.capabilities(), systemd=args.systemd)
        return 0
    raise ParseError(f"Unknown command {command!r}. Try: {', '.join(COMMANDS)}.")


def _command(args: argparse.Namespace) -> str:
    if args.command not in COMMANDS:
        raise ParseError(f"Unknown command {args.command!r}. Try: {', '.join(COMMANDS)}.")
    if args.command != "add":
        return args.command
    if args.edit:
        return "edit"
    if args.list:
        return "list"
    if args.sync:
        return "sync"
    if args.today:
        return "today"
    if args.find:
        return "find"
    if args.init:
        return "init"
    if args.install_sync:
        return "install-sync"
    return "add"


def _add(args: argparse.Namespace, config) -> int:
    config.require_vikunja()
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    title = " ".join(args.title) if args.title else ""
    if args.save or not interactive:
        if not interactive and not args.save:
            raise ParseError("A terminal is required for the form. Pass --title, --when, and --save.")
        if not title or not args.when:
            raise ParseError("Pass --title and --when, or run remindban with no arguments to use the form.")
        draft = resolve_composer(
            ComposerState(title=title, when_text=args.when, notes=args.notes or "", labels=args.labels or ""),
        )
        draft = _with_start(draft, args.starts_on)
        card = Board(config, open_backend(config)).add(draft)
        print(format_saved(card), end="")
        return 0

    result = run_composer(
        ComposerState(title=title, when_text=args.when or "", notes=args.notes or "", labels=args.labels or ""),
        intake=config.buckets.intake.title,
    )
    if result is None:
        print("Cancelled.")
        return 0
    draft = _with_start(resolve_composer(result), args.starts_on)
    card = Board(config, open_backend(config)).add(draft)
    print(format_saved(card), end="")
    return 0


def _with_start(draft, starts_on: str | None):
    if not starts_on:
        return draft
    parsed = apply_starts_on(ParsedWhen(due=draft.due, repeat=draft.repeat), starts_on)
    return replace(draft, due=parsed.due)


def _edit(path: Path) -> None:
    created = ensure_config_file(path)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    if created:
        print(f"Created {path}")
    try:
        completed = subprocess.run([*shlex.split(editor), str(path)], check=False)
    except OSError as exc:
        raise ConfigError(f"Could not start editor {editor!r}: {exc.strerror or exc}") from exc
    if completed.returncode != 0:
        raise ConfigError(f"Editor {editor!r} exited {completed.returncode}.")


def _run_sync(board: Board, *, dry_run: bool) -> None:
    capabilities = board.backend.capabilities()
    if capabilities.derived_buckets:
        print(capabilities.reason)
        print("Sync left the board alone.")
        return
    actions = board.sync(date.today(), dry_run=dry_run)
    print(format_sync(actions, dry_run=dry_run), end="")


def _install(config, capabilities: BackendCapabilities, *, systemd: bool) -> None:
    if capabilities.derived_buckets:
        print(capabilities.reason)
        print("No timer installed.")
        return
    if not config.sync.enabled:
        raise ConfigError(
            "sync.enabled is false, so no timer was installed. "
            "Turn it on, or run `remindban sync` yourself."
        )
    if systemd:
        path = install_systemd(config.sync.at)
        print(f"Enabled {path}")
    else:
        print(f"Installed {install_cron(config.sync.at)}")
    _explain_today(capabilities, config.sync.at)


def _print_today(board: Board, today: date) -> None:
    rows = today_cards(board.cards(), today)
    derived = board.config.buckets.derived.title
    print(f"{derived} from date labels on or before {today.isoformat()}")
    if not rows:
        print("  (nothing)")
        return
    for card in rows:
        marker = ""
        if card.bucket.casefold() != derived.casefold():
            marker = "  (sync will move this)"
        print(f"{format_card_line(card)}  in {card.bucket or 'no bucket'}{marker}")


def _print_find(board: Board, query: str) -> None:
    needle = query.casefold()
    matches = []
    for card in board.cards():
        haystack = " ".join(
            [
                card.title,
                card.notes,
                card.identifier,
                card.bucket,
                card.due.isoformat() if card.due else "",
                *effective_labels(card),
            ]
        ).casefold()
        if needle in haystack:
            matches.append(card)
    if not matches:
        print(f"No cards match {query!r}.")
        return
    for card in matches:
        print(f"{format_card_line(card)}  in {card.bucket or 'no bucket'}")


def _query(args: argparse.Namespace) -> str:
    text = args.find or " ".join(args.rest)
    text = text.strip()
    if not text:
        raise ParseError("Tell remindban what to find. Example: remindban find laundry")
    return text


def _explain_today(capabilities: BackendCapabilities, at: str) -> None:
    if capabilities.derived_buckets:
        print(capabilities.reason)
        return
    print(capabilities.reason)
    print(f"Run `remindban sync` to fill Today. `remindban install-sync` schedules it at {at}.")


if __name__ == "__main__":
    main()
