# RemindBan

RemindBan files reminders as cards on a kanban board. Vikunja is the only provider in v1. When it is configured, cards are written to the project titled **Remindban**.

## Branching

This repo uses `main`. Cut ticket branches from `main` and name them `tjw-###` (lowercase). Open pull requests back into `main`.

Commit messages start with the ticket ref, for example `TJW-416: short summary`.

## Where things live

- `src/remindban/kanban.py` is the backend interface. A new kanban tool is a new class plus a branch in `open_backend`. Vikunja is `vikunja.py` and speaks API v2.
- `src/remindban/buckets.py` is the bucket catalog. v1 always uses Backlog, Today, In Progress, and Done. `buckets.configurable: true` is rejected on purpose.
- Today is **derived**. A card belongs there when any label contains an ISO date (`YYYY-MM-DD`) on or before today. Vikunja cannot keep manual columns and also compute that column, so `remindban sync` moves cards. Do not pull cards out of In Progress or Done.
- New cards go to Backlog. The due date is the reminder date, and the same day is stored as a bare date label.
- Repeat rules map onto Vikunja 2.6 `repeat_after` (seconds) and `repeat_mode` (`0` interval, `1` monthly, `2` from the current date). See [docs/repeating-tasks.md](docs/repeating-tasks.md).

## Checks

```bash
python3 -m pytest
```

## Vikunja

Use the loopback API (`vikunja.api_root`, normally `http://127.0.0.1:3456/api/v1`). RemindBan rewrites that to `/api/v2`. Do not call `https://v.tyler.cloud/api/v1`; Authentik sits in front of that host.

Do not print `vikunja.api_token` or any other secret.

## Scope

Ask before fixing unrelated bugs.
