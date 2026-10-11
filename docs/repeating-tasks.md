# Repeating tasks

Vikunja's user docs describe what happens when a repeating task is marked done: the next occurrence is created from the recurrence rule. See [Dates & Reminders](https://vikunja.io/help/dates-and-reminders/).

RemindBan stores that rule with the fields Vikunja 2.6 actually accepts on a task:

| `repeat_mode` | Meaning |
| --- | --- |
| `0` | Add `repeat_after` seconds to the previous due date. |
| `1` | Monthly, on the due date's day of the month. `repeat_after` is ignored. |
| `2` | Add `repeat_after` seconds to the completion date instead of the previous due date. |

`repeat_after` is a number of seconds. A week is `604800`. A year is stored as `365` days (`31536000`). Vikunja has no calendar-year mode, so a yearly reminder can drift by a day after a leap year. The form says so.

## Phrases

| Phrase | First due date | Vikunja fields |
| --- | --- | --- |
| `tomorrow`, `friday`, `12 Oct`, `2026-10-12` | that day | no repeat |
| `every day`, `daily` | today | mode `0`, 1 day |
| `every 3 days` | today | mode `0`, 3 days |
| `every 2 weeks`, `biweekly` | today | mode `0`, 2 weeks |
| `every 2 tuesdays` | the next Tuesday, including today | mode `0`, 2 weeks |
| `every month`, `monthly` | today | mode `1` |
| `every december 1` | the next December 1 | mode `0`, 365 days |
| `every year` | today | mode `0`, 365 days |
| `every 2 weeks from completion` | today | mode `2`, 2 weeks |

The form can override the phrase: match it, do not repeat, an interval, monthly, or from the day you complete it. `--starts-on 2026-11-02` keeps the repeat and changes the first due date.

These are rejected, with a message that says what to use instead:

- `every 2 months`, because monthly mode is always one month
- `first tuesday of the month` and the other "nth weekday" rules, which Vikunja 2.6 cannot store
- `tomorrow from completion`, because that mode needs an interval

Marking the card done is what makes Vikunja schedule the next copy. On the following sync, RemindBan replaces the old date label with the new due date. If that date is still in the future and the card is sitting in Today, sync moves it back to Backlog. In Progress and Done are left where they are.
