import subprocess
from pathlib import Path

import pytest

from remindban.errors import ScheduleError
from remindban.schedule import cron_line, install_cron, install_systemd, render_crontab, systemd_units


def test_cron_line_uses_configured_time():
    line = cron_line("03:00", "/usr/local/bin/remindban sync")
    assert line == "0 3 * * * /usr/local/bin/remindban sync # remindban-sync"


def test_render_replaces_previous_sync_and_keeps_other_jobs():
    existing = "\n".join(
        [
            "15 4 * * * remind --generate",
            "# keep this comment about remindban sync",
            "0 4 * * * /home/tyler/.local/bin/remindban sync",
            "",
        ]
    )
    updated = render_crontab(existing, cron_line("03:05", "remindban sync"))
    assert "remind --generate" in updated
    assert "keep this comment" in updated
    assert "/home/tyler/.local/bin/remindban sync" not in updated
    assert updated.strip().endswith("5 3 * * * remindban sync # remindban-sync")


def test_install_cron_writes_when_user_has_no_crontab():
    seen = {}

    def run(args, **kwargs):
        seen["args"] = args
        seen["input"] = kwargs.get("input")
        if args == ["crontab", "-l"]:
            return subprocess.CompletedProcess(args, 1, "", "no crontab for tyler")
        return subprocess.CompletedProcess(args, 0, "", "")

    line = install_cron("03:00", run=run)
    assert seen["args"] == ["crontab", "-"]
    assert seen["input"] == line + "\n"


def test_install_cron_reports_crontab_failure():
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "permission denied")

    with pytest.raises(ScheduleError, match="permission denied"):
        install_cron("03:00", run=run)


def test_systemd_unit_uses_the_configured_clock(tmp_path: Path):
    service, timer = systemd_units("15:45", "/usr/bin/remindban sync")
    assert "ExecStart=/usr/bin/remindban sync" in service
    assert "OnCalendar=*-*-* 15:45:00" in timer

    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "", "")

    path = install_systemd("15:45", home=tmp_path, run=run)
    assert path == tmp_path / ".config" / "systemd" / "user" / "remindban-sync.timer"
    assert "15:45:00" in path.read_text(encoding="utf-8")
