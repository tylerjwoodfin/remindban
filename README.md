# RemindBan

Reminders on a kanban board.

RemindMail sends reminders by email and keeps them in a YAML file. RemindBan keeps them as cards. You add one from the terminal, it lands in **Backlog** with a due date, and a date label decides when it belongs in **Today**. Vikunja is the only board in v1. The code talks to a small backend interface, so another board can be added later without rewriting the form or the sync.

## Buckets

v1 always uses these four. Custom buckets are rejected until a later release; the catalog is already the type sync and the Vikunja adapter share.

| Bucket | What it is |
| --- | --- |
| Backlog | New reminders. Also where a future-dated card returns after it repeats. |
| Today | Cards with a label that contains today's date or an earlier one. |
| In Progress | Left alone by sync. |
| Done | Left alone by sync. In Vikunja, moving a card here marks it done. |

Today is a derived bucket. Vikunja cannot compute "a label contains a date on or before today" and still keep the other columns manual, so RemindBan moves those cards itself. `remindban today` shows the derived set immediately. The Today column on the board catches up when `remindban sync` runs.

## Install

```bash
pip install -e .
remindban --edit
```

Python 3.11 or newer. Dependencies are `requests`, `PyYAML`, `prompt_toolkit`, and `python-dateutil`.

## Configuration

`remindban edit` creates `~/.config/remindban/config.yml` and opens it. A copy of the starter file is `config.example.yml`. The path is, in order, `--file`, `REMINDBAN_CONFIG`, Cabinet key `remindban.path.file`, then that default.

```yaml
kanban:
  provider: vikunja
  project: Remindban

vikunja:
  # Blank values fall through to the environment, then Cabinet.
  # Cabinet keys: vikunja.api_root, vikunja.api_token, vikunja.base_url
  api_root: ""
  base_url: ""
  api_token: ""

buckets:
  configurable: false

sync:
  enabled: true
  time: "03:00"
```

`sync.time` is local 24-hour `HH:MM`. `03:00` is the default; `15:45` is a valid choice. The API root may be either `/api/v1` or `/api/v2`. RemindBan calls v2.

Use the loopback API (`http://127.0.0.1:3456/api/v1` in Cabinet). The public host sits behind Authentik and is only used for links.

`remindban init` creates the **Remindban** project if it is missing, adds the four buckets, and points Vikunja's default bucket at Backlog and its done bucket at Done.

## Usage

```bash
remindban                                  # form: title, when, repeat, notes, labels
remindban --title 'Call mom' --when 'friday' --save
remindban --title 'Laundry' --when 'every 2 weeks' --starts-on 2026-11-02 --save
remindban list
remindban today
remindban find laundry
remindban sync                             # move due backlog cards into Today
remindban sync --dry-run
remindban install-sync                     # crontab at sync.time
remindban install-sync --systemd           # user timer instead
remindban edit
remindban init
```

In the form, Tab moves, Ctrl-S saves, Esc cancels, and the left and right arrows change Repeat and Unit when those rows are focused. The preview shows the backlog bucket, the due date, the date label, and the repeat Vikunja will store. A phrase it cannot store is explained in the preview instead of being saved as a guess.

`--when` accepts the same kind of language as RemindMail: `tomorrow`, `friday`, `12 Oct`, `2026-10-12`, `in 3 weeks`, `every 2 tuesdays`, `every month`, `every december 1`. Repeat details, including the Vikunja modes, are in [docs/repeating-tasks.md](docs/repeating-tasks.md).

### Filling Today

Vikunja will not move cards into Today on its own. A cron line at 3am:

```bash
remindban install-sync
```

That installs the equivalent of:

```cron
0 3 * * * remindban sync # remindban-sync
```

The minute and hour come from `sync.time`. Running the installer again replaces the previous RemindBan line and leaves the rest of the crontab.

Sync updates the bare `YYYY-MM-DD` label so it matches the due date, then:

- moves a card into Today when that label, or any label containing an ISO date, is today or earlier
- moves a card from Today back to Backlog when its date is still in the future
- does not move In Progress or Done

## How it is put together

[docs/architecture.md](docs/architecture.md) describes the backend interface, the bucket roles, and why Today is synced instead of filtered.

## License

MIT. See [LICENSE.md](LICENSE.md).

## Disclaimer

This is a non-commercial, open-source project. Your board is your responsibility. Take appropriate precautions with API tokens.

## Author

Tyler Woodfin  
[https://tyler.cloud](https://tyler.cloud)  
[feedback-remindban@tyler.cloud](mailto:feedback-remindban@tyler.cloud)
