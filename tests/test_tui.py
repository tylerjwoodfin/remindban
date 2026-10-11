from datetime import date

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from remindban.compose import resolve_composer
from remindban.tui import run_composer

TODAY = date(2026, 10, 10)


def test_ctrl_s_saves_the_form_and_escape_cancels():
    with create_pipe_input() as pipe:
        pipe.send_text("Call mom\ttomorrow\x13")
        saved = run_composer(input=pipe, output=DummyOutput(), today=TODAY)
    assert saved is not None
    draft = resolve_composer(saved, today=TODAY)
    assert draft.title == "Call mom"
    assert draft.due == date(2026, 10, 11)

    with create_pipe_input() as pipe:
        pipe.send_text("\x1b")
        assert run_composer(input=pipe, output=DummyOutput(), today=TODAY) is None
