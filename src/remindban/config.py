"""Load RemindBan's YAML config and fill gaps from the environment or Cabinet."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from remindban.buckets import BucketCatalog
from remindban.errors import ConfigError

DEFAULT_PROJECT = "Remindban"
DEFAULT_API_ROOT = "http://127.0.0.1:3456/api/v1"
DEFAULT_BASE_URL = "https://v.tyler.cloud"
DEFAULT_SYNC_TIME = "03:00"
_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class VikunjaSettings:
    api_root: str
    base_url: str
    api_token: str


@dataclass(frozen=True)
class SyncSettings:
    enabled: bool
    at: str


@dataclass(frozen=True)
class AppConfig:
    path: Path
    provider: str
    project: str
    vikunja: VikunjaSettings
    buckets: BucketCatalog
    sync: SyncSettings

    def require_vikunja(self) -> VikunjaSettings:
        if not self.vikunja.api_token:
            raise ConfigError(
                "Vikunja API token is not set. Add vikunja.api_token to "
                f"{self.path}, export VIKUNJA_API_TOKEN, or set Cabinet key "
                "vikunja.api_token. Run `remindban edit` to open the file."
            )
        return self.vikunja


def default_config_path() -> Path:
    return Path.home() / ".config" / "remindban" / "config.yml"


def resolve_config_path(
    explicit: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    env = environ if environ is not None else os.environ
    if explicit:
        return Path(explicit).expanduser()
    from_env = str(env.get("REMINDBAN_CONFIG") or "").strip()
    if from_env:
        return Path(from_env).expanduser()
    from_cabinet = _cabinet_get("remindban", "path", "file")
    if from_cabinet:
        return Path(from_cabinet).expanduser()
    return default_config_path()


def load_config(
    explicit: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    env = environ if environ is not None else os.environ
    path = resolve_config_path(explicit, environ=env)
    data = _read_yaml(path)
    provider = str(_dig(data, "kanban", "provider") or "vikunja").strip().lower()
    if provider != "vikunja":
        raise ConfigError(
            f"Kanban provider {provider!r} is not available. RemindBan v1 supports vikunja only."
        )
    buckets_section = data.get("buckets") or {}
    if isinstance(buckets_section, dict) and buckets_section.get("configurable"):
        raise ConfigError(
            "Custom buckets are not available in RemindBan v1. "
            "Leave buckets.configurable set to false."
        )
    project = str(_dig(data, "kanban", "project") or DEFAULT_PROJECT).strip()
    if not project:
        raise ConfigError("kanban.project cannot be empty.")
    return AppConfig(
        path=path,
        provider=provider,
        project=project,
        vikunja=VikunjaSettings(
            api_root=normalize_api_root(_first(
                _dig(data, "vikunja", "api_root"),
                env.get("VIKUNJA_API_ROOT"),
                _cabinet_get("vikunja", "api_root"),
                DEFAULT_API_ROOT,
            )),
            base_url=_first(
                _dig(data, "vikunja", "base_url"),
                env.get("VIKUNJA_BASE_URL"),
                _cabinet_get("vikunja", "base_url"),
                DEFAULT_BASE_URL,
            ).rstrip("/"),
            api_token=_first(
                _dig(data, "vikunja", "api_token"),
                env.get("VIKUNJA_API_TOKEN"),
                _cabinet_get("vikunja", "api_token"),
                "",
            ),
        ),
        buckets=BucketCatalog.defaults(),
        sync=SyncSettings(
            enabled=_bool(_dig(data, "sync", "enabled"), default=True),
            at=normalize_sync_time(_dig(data, "sync", "time") or DEFAULT_SYNC_TIME),
        ),
    )


def normalize_api_root(value: str) -> str:
    root = value.strip().rstrip("/")
    for suffix in ("/api/v1", "/api/v2"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
    if not root:
        raise ConfigError("vikunja.api_root cannot be empty.")
    return root + "/api/v2"


def normalize_sync_time(value: object) -> str:
    text = str(value).strip()
    match = _TIME.fullmatch(text)
    if not match:
        raise ConfigError(
            f"sync.time must be 24-hour HH:MM (for example {DEFAULT_SYNC_TIME}). Got {text!r}."
        )
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ConfigError(
            f"sync.time must be 24-hour HH:MM (for example {DEFAULT_SYNC_TIME}). Got {text!r}."
        )
    return f"{hour:02d}:{minute:02d}"


def example_config() -> str:
    return """\
# RemindBan
# Open this file again with: remindban edit

kanban:
  # v1 ships with one provider. Adapters live behind the same interface.
  provider: vikunja
  project: Remindban

vikunja:
  # Leave a value blank to use the matching environment variable or Cabinet key.
  # Cabinet keys: vikunja.api_root, vikunja.api_token, vikunja.base_url
  api_root: ""
  base_url: ""
  api_token: ""

# Buckets are fixed in v1: Backlog, Today, In Progress, and Done.
# Today is derived from date labels. The catalog type can grow later;
# setting configurable to true is rejected until then.
buckets:
  configurable: false

sync:
  # Local time for `remindban install-sync`. The command itself is `remindban sync`.
  enabled: true
  time: "03:00"
"""


def ensure_config_file(path: Path) -> bool:
    """Create a starter config if needed. Returns True when a file was created."""

    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(example_config(), encoding="utf-8")
    return True


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc.strerror or exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"{path} must be a YAML mapping.")
    return loaded


def _dig(data: Mapping[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _first(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"Expected true or false, got {value!r}.")


def _cabinet_get(*keys: str) -> str:
    try:
        from cabinet import Cabinet
    except ImportError:
        return ""
    try:
        value = Cabinet().get(*keys, return_type=str) or ""
    except Exception:
        return ""
    return str(value).strip()
