from datetime import date

import pytest

from remindban.compose import ComposerState, preview_message, resolve_composer
from remindban.errors import ParseError
from remindban.models import RepeatMode

TODAY = date(2026, 10, 10)


def test_resolve_uses_the_phrase_until_the_form_overrides_it():
    draft = resolve_composer(
        ComposerState(title="  Call   mom ", when_text="every 2 weeks", labels="home, phone"),
        today=TODAY,
    )
    assert draft.title == "Call mom"
    assert draft.due == TODAY
    assert draft.labels == ("home", "phone")
    assert draft.repeat.to_vikunja() == (2 * 7 * 86400, 0)
    assert draft.date_label == "2026-10-10"

    overridden = resolve_composer(
        ComposerState(
            title="Call mom",
            when_text="every 2 weeks",
            repeat_choice="from_completion",
            every="3",
            unit="days",
        ),
        today=TODAY,
    )
    assert overridden.repeat.mode is RepeatMode.FROM_CURRENT_DATE
    assert overridden.repeat.to_vikunja() == (3 * 86400, 2)


def test_preview_explains_what_is_missing_and_what_will_be_saved():
    missing = preview_message(ComposerState(when_text="tomorrow"), today=TODAY)
    assert "title" in missing
    ready = preview_message(ComposerState(title="Laundry", when_text="tomorrow"), today=TODAY)
    assert "Backlog" in ready
    assert "2026-10-11" in ready
    assert "Does not repeat" in ready


def test_blank_every_is_rejected():
    with pytest.raises(ParseError, match="whole number"):
        resolve_composer(
            ComposerState(title="Laundry", when_text="friday", repeat_choice="interval", every="0"),
            today=TODAY,
        )
