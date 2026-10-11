"""Full-screen composer for a new reminder.

The form is a short stack of labeled fields plus a live preview. Ctrl-S saves.
Esc cancels. Left and right change Repeat and Unit when those rows are focused.
"""

from __future__ import annotations

from datetime import date

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from remindban.compose import REPEAT_CHOICES, UNITS, ComposerState, preview_message, resolve_composer

STYLE = Style.from_dict(
    {
        "header": "bg:#1e1e2e #cdd6f4 bold",
        "accent": "#89b4fa",
        "muted": "#6c7086",
        "ok": "#a6e3a1",
        "warn": "#f9e2af",
        "bad": "#f38ba8",
        "preview": "#cdd6f4",
        "status": "bg:#181825 #a6adc8",
        "status.key": "bg:#181825 #f9e2af bold",
        "text-area": "bg:#313244 #cdd6f4",
        "text-area.prompt": "bg:#313244 #89b4fa",
    }
)


def run_composer(
    initial: ComposerState | None = None,
    *,
    today: date | None = None,
    intake: str = "Backlog",
    input=None,
    output=None,
) -> ComposerState | None:
    """Edit a reminder. Returns the form state, or None when the user cancels."""

    state = initial or ComposerState()
    anchor = today or date.today()
    saved: dict[str, ComposerState | None] = {"result": None}
    repeat_index = _index(REPEAT_CHOICES, state.repeat_choice)
    unit_index = UNITS.index(state.unit) if state.unit in UNITS else 1

    title = _field("Title   ", state.title)
    when = _field("When    ", state.when_text)
    every = _field("Every   ", state.every or "1")
    notes = TextArea(text=state.notes, height=2, multiline=True, wrap_lines=True, prompt=HTML("<accent>Notes   </accent>"))
    labels = _field("Labels  ", state.labels)
    repeat = _field("Repeat  ", REPEAT_CHOICES[repeat_index][1], read_only=True)
    unit = _field("Unit    ", UNITS[unit_index], read_only=True)

    def snapshot() -> ComposerState:
        return ComposerState(
            title=title.text,
            when_text=when.text,
            notes=notes.text,
            labels=labels.text,
            repeat_choice=REPEAT_CHOICES[repeat_index][0],
            every=every.text,
            unit=UNITS[unit_index],
        )

    def preview():
        current = snapshot()
        message = preview_message(current, today=anchor, intake=intake)
        try:
            resolve_composer(current, today=anchor)
            style = "class:preview"
        except Exception:
            style = "class:bad"
        return FormattedText([(style, message)])

    holder: dict[str, Application] = {}

    def cycling() -> bool:
        layout = holder["app"].layout
        return layout.has_focus(repeat) or layout.has_focus(unit)

    bindings = KeyBindings()

    @bindings.add("c-s", eager=True)
    def _save(event) -> None:
        del event
        try:
            resolve_composer(snapshot(), today=anchor)
        except Exception:
            return
        saved["result"] = snapshot()
        holder["app"].exit()

    @bindings.add("escape", eager=True)
    def _cancel(event) -> None:
        del event
        holder["app"].exit()

    @bindings.add("tab", eager=True)
    def _next(event) -> None:
        event.app.layout.focus_next()

    @bindings.add("s-tab", eager=True)
    def _previous(event) -> None:
        event.app.layout.focus_previous()

    @bindings.add("right", filter=Condition(cycling))
    def _cycle_forward(event) -> None:
        nonlocal repeat_index, unit_index
        if event.app.layout.has_focus(repeat):
            repeat_index = (repeat_index + 1) % len(REPEAT_CHOICES)
            repeat.text = REPEAT_CHOICES[repeat_index][1]
        else:
            unit_index = (unit_index + 1) % len(UNITS)
            unit.text = UNITS[unit_index]

    @bindings.add("left", filter=Condition(cycling))
    def _cycle_back(event) -> None:
        nonlocal repeat_index, unit_index
        if event.app.layout.has_focus(repeat):
            repeat_index = (repeat_index - 1) % len(REPEAT_CHOICES)
            repeat.text = REPEAT_CHOICES[repeat_index][1]
        else:
            unit_index = (unit_index - 1) % len(UNITS)
            unit.text = UNITS[unit_index]

    body = HSplit(
        [
            Window(
                FormattedTextControl(
                    HTML("<header> RemindBan </header><header>  new reminder, saved to the backlog</header>")
                ),
                height=1,
            ),
            title,
            when,
            Window(
                FormattedTextControl(
                    HTML("<muted>  tomorrow · friday · 12 Oct · 2026-10-12 · every 2 weeks · every month</muted>")
                ),
                height=1,
            ),
            repeat,
            every,
            unit,
            notes,
            labels,
            Window(
                FormattedTextControl(
                    HTML("<muted>  Labels are comma-separated. The due date is added on its own.</muted>")
                ),
                height=1,
            ),
            Window(char="─", height=1),
            Window(FormattedTextControl(preview), height=Dimension(min=4, weight=1)),
            Window(
                FormattedTextControl(
                    lambda: [
                        ("class:status.key", " Ctrl-S "),
                        ("class:status", " save  "),
                        ("class:status.key", " Esc "),
                        ("class:status", " cancel  "),
                        ("class:status.key", " Tab "),
                        ("class:status", " next  "),
                        ("class:status.key", " ← → "),
                        ("class:status", " repeat and unit "),
                    ]
                ),
                height=1,
            ),
        ]
    )
    app: Application = Application(
        layout=Layout(body, focused_element=title),
        key_bindings=bindings,
        style=STYLE,
        full_screen=True,
        mouse_support=True,
        input=input,
        output=output,
    )
    holder["app"] = app
    app.run()
    return saved["result"]


def _field(prompt: str, text: str, *, read_only: bool = False) -> TextArea:
    return TextArea(
        text=text,
        height=1,
        multiline=False,
        wrap_lines=False,
        read_only=read_only,
        prompt=HTML(f"<accent>{prompt}</accent>"),
    )


def _index(choices: tuple[tuple[str, str], ...], value: str) -> int:
    for index, (key, _label) in enumerate(choices):
        if key == value:
            return index
    return 0
