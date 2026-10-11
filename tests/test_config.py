from pathlib import Path

import pytest

from remindban.config import example_config, load_config, normalize_api_root, normalize_sync_time
from remindban.errors import ConfigError


def test_api_root_versions_collapse_to_v2():
    assert normalize_api_root("http://127.0.0.1:3456/api/v1") == "http://127.0.0.1:3456/api/v2"
    assert normalize_api_root("http://127.0.0.1:3456/api/v2/") == "http://127.0.0.1:3456/api/v2"


def test_sync_time_normalizes_and_rejects_garbage():
    assert normalize_sync_time("3:00") == "03:00"
    assert normalize_sync_time("23:59") == "23:59"
    with pytest.raises(ConfigError, match="HH:MM"):
        normalize_sync_time("3am")
    with pytest.raises(ConfigError, match="HH:MM"):
        normalize_sync_time("24:00")


def test_missing_file_uses_defaults_and_env(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("remindban.config._cabinet_get", lambda *keys: "")
    path = tmp_path / "missing.yml"
    config = load_config(str(path), environ={"VIKUNJA_API_TOKEN": "secret-token", "REMINDBAN_CONFIG": ""})
    assert config.project == "Remindban"
    assert config.provider == "vikunja"
    assert config.vikunja.api_token == "secret-token"
    assert config.vikunja.api_root.endswith("/api/v2")
    assert config.sync.at == "03:00"
    assert config.buckets.derived.title == "Today"
    assert "secret-token" not in example_config()


def test_file_overrides_env_and_custom_buckets_are_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("remindban.config._cabinet_get", lambda *keys: "from-cabinet")
    path = tmp_path / "config.yml"
    path.write_text(
        """
kanban:
  provider: vikunja
  project: Remindban
vikunja:
  api_root: http://example.test/api/v1
  api_token: from-file
sync:
  time: "4:15"
""",
        encoding="utf-8",
    )
    config = load_config(str(path), environ={"VIKUNJA_API_TOKEN": "from-env"})
    assert config.vikunja.api_token == "from-file"
    assert config.vikunja.api_root == "http://example.test/api/v2"
    assert config.sync.at == "04:15"

    path.write_text("buckets:\n  configurable: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Custom buckets"):
        load_config(str(path), environ={})


def test_unknown_provider(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("remindban.config._cabinet_get", lambda *keys: "")
    path = tmp_path / "config.yml"
    path.write_text("kanban:\n  provider: trello\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="vikunja only"):
        load_config(str(path), environ={})
