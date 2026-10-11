from datetime import date

from remindban.buckets import BucketCatalog
from remindban.models import Card
from remindban.sync import Move, Relabel, belongs_in_today, plan_sync

TODAY = date(2026, 10, 10)
CATALOG = BucketCatalog.defaults()


def card(**kwargs) -> Card:
    base = dict(
        id="1",
        identifier="REMINDBAN-1",
        title="Pay rent",
        notes="",
        due=None,
        labels=(),
        bucket="Backlog",
        done=False,
    )
    base.update(kwargs)
    return Card(**base)


def test_label_dates_on_or_before_today_qualify():
    assert belongs_in_today(("2026-10-10",), TODAY)
    assert belongs_in_today(("before:2026-10-01",), TODAY)
    assert not belongs_in_today(("2026-10-11",), TODAY)
    assert not belongs_in_today(("2026-02-31", "home"), TODAY)
    assert not belongs_in_today(("home",), TODAY)


def test_backlog_card_due_today_is_labeled_and_moved():
    actions = plan_sync([card(due=TODAY)], CATALOG, TODAY)
    assert actions == [
        Relabel(card(due=TODAY), ("2026-10-10",)),
        Move(card(due=TODAY), "Today"),
    ]


def test_future_card_in_today_returns_to_backlog():
    source = card(id="4", due=date(2026, 10, 20), labels=("2026-10-01",), bucket="Today")
    actions = plan_sync([source], CATALOG, TODAY)
    assert actions == [
        Relabel(source, ("2026-10-20",)),
        Move(source, "Backlog"),
    ]


def test_in_progress_and_done_are_not_moved():
    active = card(id="2", due=TODAY, bucket="In Progress", labels=("home",))
    finished = card(id="3", due=TODAY, bucket="Backlog", done=True)
    actions = plan_sync([active, finished], CATALOG, TODAY)
    assert actions == [Relabel(active, ("home", "2026-10-10"))]


def test_already_correct_today_card_is_left_alone():
    source = card(due=TODAY, labels=("2026-10-10", "home"), bucket="Today")
    assert plan_sync([source], CATALOG, TODAY) == []
