import subprocess
from datetime import date

import pytest

from remindban.cli import execute
from remindban.models import BackendCapabilities, Card, RepeatSpec
from remindban.service import format_sync


class FakeBackend:
    def __init__(self, cards=None, *, derived=False):
        self.cards_on_board = list(cards or [])
        self.created = []
        self.moved = []
        self.relabeled = []
        self.prepared = False
        self.derived = derived

    def capabilities(self):
        if self.derived:
            return BackendCapabilities(True, "This board derives Today itself.")
        return BackendCapabilities(False, "This board cannot derive Today.")

    def ensure_layout(self):
        self.prepared = True

    def create_reminder(self, draft):
        self.created.append(draft)
        return Card(
            id="9",
            identifier="REMINDBAN-9",
            title=draft.title,
            notes=draft.notes,
            due=draft.due,
            labels=(draft.date_label, *draft.labels),
            bucket="Backlog",
            done=False,
            repeat_after=draft.repeat.to_vikunja()[0],
            repeat_mode=draft.repeat.to_vikunja()[1],
            url="https://v.tyler.cloud/tasks/9",
        )

    def list_cards(self):
        return self.cards_on_board

    def move_card(self, card_id, bucket):
        self.moved.append((card_id, bucket))

    def update_labels(self, card, labels):
        self.relabeled.append((card.id, labels))


def card(**kwargs) -> Card:
    base = dict(
        id="1",
        identifier="REMINDBAN-1",
        title="Pay rent",
        notes="",
        due=date(2026, 10, 10),
        labels=(),
        bucket="Backlog",
        done=False,
    )
    base.update(kwargs)
    return Card(**base)


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr("remindban.config._cabinet_get", lambda *keys: "")
    monkeypatch.delenv("VIKUNJA_API_TOKEN", raising=False)
    monkeypatch.delenv("VIKUNJA_API_ROOT", raising=False)
    monkeypatch.delenv("VIKUNJA_BASE_URL", raising=False)
    path = tmp_path / "config.yml"
    path.write_text("vikunja:\n  api_token: test-token\n", encoding="utf-8")
    return path


def test_save_writes_a_backlog_card(configured, monkeypatch, capsys):
    fake = FakeBackend()
    monkeypatch.setattr("remindban.cli.open_backend", lambda config: fake)
    code = execute(
        ["--file", str(configured), "--title", "Call", "mom", "--when", "2026-10-12", "--save", "--labels", "home"]
    )
    assert code == 0
    assert fake.created[0].title == "Call mom"
    assert fake.created[0].due == date(2026, 10, 12)
    assert fake.created[0].labels == ("home",)
    assert fake.created[0].repeat == RepeatSpec.none()
    output = capsys.readouterr().out
    assert "REMINDBAN-9" in output
    assert "Backlog" in output
    assert "https://v.tyler.cloud/tasks/9" in output


def test_sync_moves_a_due_backlog_card(configured, monkeypatch, capsys):
    fake = FakeBackend([card()])
    monkeypatch.setattr("remindban.cli.open_backend", lambda config: fake)
    assert execute(["--file", str(configured), "sync", "--dry-run"]) == 0
    assert fake.moved == []
    dry = capsys.readouterr().out
    assert "Would move" in dry

    assert execute(["--file", str(configured), "--sync"]) == 0
    assert fake.relabeled == [("1", ("2026-10-10",))]
    assert fake.moved == [("1", "Today")]


def test_today_and_find_do_not_move_cards(configured, monkeypatch, capsys):
    fake = FakeBackend([card(title="Laundry day", labels=("home",))])
    monkeypatch.setattr("remindban.cli.open_backend", lambda config: fake)
    assert execute(["--file", str(configured), "today"]) == 0
    assert execute(["--file", str(configured), "find", "laundry"]) == 0
    assert fake.moved == []
    output = capsys.readouterr().out
    assert "sync will move this" in output
    assert "Laundry day" in output


def test_init_and_missing_token(configured, monkeypatch, capsys, tmp_path):
    fake = FakeBackend()
    monkeypatch.setattr("remindban.cli.open_backend", lambda config: fake)
    assert execute(["--file", str(configured), "init"]) == 0
    assert fake.prepared
    assert "Remindban" in capsys.readouterr().out

    empty = tmp_path / "empty.yml"
    empty.write_text("kanban:\n  provider: vikunja\n", encoding="utf-8")
    code = execute(["--file", str(empty), "list"])
    assert code == 1
    assert "api_token" in capsys.readouterr().err


def test_edit_creates_a_config_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("remindban.config._cabinet_get", lambda *keys: "")
    path = tmp_path / "config.yml"
    monkeypatch.setattr(
        "remindban.cli.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0),
    )
    assert execute(["--file", str(path), "--edit"]) == 0
    text = path.read_text(encoding="utf-8")
    assert "project: Remindban" in text
    assert "time: \"03:00\"" in text
    assert "Created" in capsys.readouterr().out


def test_install_sync_skips_a_board_that_derives_today(configured, monkeypatch, capsys):
    fake = FakeBackend(derived=True)
    monkeypatch.setattr("remindban.cli.open_backend", lambda config: fake)
    called = {}
    monkeypatch.setattr("remindban.cli.install_cron", lambda at: called.setdefault("at", at))
    assert execute(["--file", str(configured), "install-sync"]) == 0
    assert called == {}
    assert "No timer installed" in capsys.readouterr().out


def test_unknown_command_and_help(capsys):
    assert execute(["nope"]) == 1
    assert "Unknown command" in capsys.readouterr().err
    assert execute(["--help"]) == 0
    assert "install-sync" in capsys.readouterr().out


def test_sync_report_for_an_empty_plan():
    assert format_sync([], dry_run=False) == "Today is already up to date.\n"
