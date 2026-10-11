# Architecture

RemindBan is a terminal client. It does not keep its own reminder database. The kanban board is the store.

```
form or flags
    -> ReminderDraft
    -> KanbanBackend.create_reminder
    -> backlog card, due date, YYYY-MM-DD label

remindban sync
    -> plan from labels and due dates
    -> move between Backlog and Today
```

## Kanban backends

`KanbanBackend` is the whole vendor surface: make sure the project and buckets exist, create a card, list cards, move a card, and update labels. `open_backend` picks the class from `kanban.provider`. v1 has one branch, `vikunja`.

Each backend reports whether it can show a derived bucket itself. Vikunja's answer is no. Its filter buckets are a fixed set of filters, and enabling them replaces manual columns, so they cannot keep Backlog, In Progress, and Done while filling Today from "a label contains a date on or before today." `remindban sync` is the fallback. A later backend that can derive the column should say so; sync and `install-sync` then leave the board alone.

## Buckets

A `BucketCatalog` is an ordered list of `BucketSpec` values. Each spec has a stable key, a title written to the board, and a role:

| Role | v1 title | Sync |
| --- | --- | --- |
| intake | Backlog | New cards land here. Future-dated cards in Today are sent back here. |
| derived | Today | Cards whose date label is today or earlier, unless they are sticky. |
| active | In Progress | Never moved by sync. |
| done | Done | Never moved by sync. Vikunja's done bucket marks a card done. |

v1 does not read custom buckets from the config file. `parse_bucket_specs` is the loader a later release can call. Sync already takes a catalog, so it does not assume the four titles except through that catalog.

## Dates

The composer parses a phrase into a due date and a `RepeatSpec`. Saving writes:

- `due_date` at noon in the local timezone, so the calendar day does not flip
- a label whose entire title is `YYYY-MM-DD`
- Vikunja `repeat_after` and `repeat_mode` when the reminder repeats

Sync treats a bare ISO-date label as RemindBan's own. It rewrites that label when the due date changes, which is what Vikunja does after a repeating card is completed. Any other label is left in place. A label still counts for Today if an ISO date appears anywhere in its title.

## Scheduling

`sync.time` is a local `HH:MM`, default `03:00`. `remindban install-sync` writes a crontab line. `--systemd` writes a user timer instead. The job runs `remindban sync`. `sync.enabled: false` refuses the installer; the command itself still runs when you call it.

## Errors

Expected failures are `RemindBanError` subclasses (`ConfigError`, `ParseError`, `KanbanError`, `ScheduleError`). The CLI prints `remindban: ...` and exits `1`. HTTP 401 and 403 name the route and do not echo the token. Vikunja uses that status both for a bad token and for a scoped token that is missing the route. Unexpected exceptions are one line unless `--debug` is set.
