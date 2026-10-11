"""Install the Today sync at the configured local time.

Cron is the default, matching RemindMail. A systemd user timer is available
when the kanban tool cannot maintain the derived bucket itself.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from remindban.errors import ScheduleError

MARKER = "# remindban-sync"
_SYNC_COMMAND = re.compile(r"(?:^|\s|/)remindban\s+.*\bsync(?:\s|$)")


def cron_expression(at: str) -> str:
    hour, minute = at.split(":")
    return f"{int(minute)} {int(hour)} * * *"


def sync_command() -> str:
    found = shutil.which("remindban")
    if found:
        return f"{found} sync"
    return f"{sys.executable} -m remindban sync"


def cron_line(at: str, command: str | None = None) -> str:
    return f"{cron_expression(at)} {command or sync_command()} {MARKER}"


def render_crontab(existing: str, line: str) -> str:
    """Replace any previous RemindBan sync entry and append ``line``."""

    kept: list[str] = []
    for row in existing.splitlines():
        stripped = row.strip()
        if not stripped.startswith("#") and (MARKER in row or _SYNC_COMMAND.search(stripped)):
            continue
        kept.append(row)
    kept.append(line)
    body = "\n".join(kept).strip()
    return f"{body}\n" if body else ""


def install_cron(at: str, *, run=subprocess.run) -> str:
    line = cron_line(at)
    try:
        listed = run(["crontab", "-l"], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ScheduleError(f"Could not read the crontab: {exc.strerror or exc}") from exc
    if listed.returncode != 0 and "no crontab" not in (listed.stderr or "").casefold():
        detail = (listed.stderr or "").strip() or f"crontab exited {listed.returncode}"
        raise ScheduleError(f"Could not read the crontab: {detail}")
    updated = render_crontab(listed.stdout or "", line)
    try:
        applied = run(["crontab", "-"], input=updated, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ScheduleError(f"Could not install the crontab: {exc.strerror or exc}") from exc
    if applied.returncode != 0:
        detail = (applied.stderr or "").strip() or f"crontab exited {applied.returncode}"
        raise ScheduleError(f"Could not install the crontab: {detail}")
    return line


def systemd_units(at: str, command: str | None = None) -> tuple[str, str]:
    executable = command or sync_command()
    service = (
        "[Unit]\n"
        "Description=Move due RemindBan cards into Today\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={executable}\n"
    )
    timer = (
        "[Unit]\n"
        "Description=RemindBan Today sync\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {at}:00\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    return service, timer


def install_systemd(at: str, *, home: Path | None = None, run=subprocess.run) -> Path:
    root = (home or Path.home()) / ".config" / "systemd" / "user"
    root.mkdir(parents=True, exist_ok=True)
    service, timer = systemd_units(at)
    service_path = root / "remindban-sync.service"
    timer_path = root / "remindban-sync.timer"
    service_path.write_text(service, encoding="utf-8")
    timer_path.write_text(timer, encoding="utf-8")
    try:
        reloaded = run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
            text=True,
            check=False,
        )
        enabled = run(
            ["systemctl", "--user", "enable", "--now", "remindban-sync.timer"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ScheduleError(
            f"Wrote {timer_path}, but systemctl is not available: {exc.strerror or exc}"
        ) from exc
    if reloaded.returncode != 0 or enabled.returncode != 0:
        detail = (enabled.stderr or reloaded.stderr or "").strip()
        raise ScheduleError(
            f"Wrote {timer_path}, but systemd did not enable it."
            + (f" {detail}" if detail else "")
        )
    return timer_path
