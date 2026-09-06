from __future__ import annotations

import pytest

from app.config import ConfigError, Settings
from app.redaction import describe_uri, redact

# Built by concatenation so the repository never contains a literal user:password@ URI.
URI_WITH_CREDENTIALS = (
    "mongodb://" + "crudapp:" + "s3cret%40pw" + "@mongodb:27017/cruddb?authSource=cruddb"
)


def test_redact_hides_userinfo_but_keeps_host() -> None:
    redacted = redact(f"connection failed for {URI_WITH_CREDENTIALS}")
    assert "s3cret" not in redacted
    assert "crudapp" not in redacted
    assert "mongodb://***@mongodb:27017/cruddb?authSource=cruddb" in redacted


def test_redact_leaves_text_without_uri_untouched() -> None:
    assert redact("plain message") == "plain message"


def test_describe_uri_drops_credentials_and_options() -> None:
    assert describe_uri(URI_WITH_CREDENTIALS) == "mongodb://mongodb:27017/cruddb"
    assert describe_uri("mongodb://mongodb:27017/cruddb") == "mongodb://mongodb:27017/cruddb"
    assert describe_uri("not a uri") == "<invalid-uri>"


def test_settings_require_uri() -> None:
    with pytest.raises(ConfigError, match="MONGODB_URI is required"):
        Settings.from_env({})


def test_settings_reject_unknown_scheme() -> None:
    with pytest.raises(ConfigError, match="mongodb://"):
        Settings.from_env({"MONGODB_URI": "http://mongodb:27017"})


def test_settings_defaults_match_runbook_contract() -> None:
    settings = Settings.from_env({"MONGODB_URI": "mongodb://mongodb:27017/cruddb"})
    assert settings.mongodb_database == "cruddb"
    assert settings.mongodb_collection == "items"
    assert settings.mongodb_ping_timeout_ms > 0


def test_settings_read_configmap_values() -> None:
    settings = Settings.from_env(
        {
            "MONGODB_URI": "mongodb://mongodb:27017/other",
            "MONGODB_DATABASE": "other",
            "MONGODB_COLLECTION": "things",
            "MONGODB_PING_TIMEOUT_MS": "750",
            "LOG_LEVEL": "debug",
        }
    )
    assert settings.mongodb_database == "other"
    assert settings.mongodb_collection == "things"
    assert settings.mongodb_ping_timeout_ms == 750
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize("value", ["0", "-5", "abc"])
def test_settings_reject_non_positive_timeouts(value: str) -> None:
    with pytest.raises(ConfigError, match="MONGODB_PING_TIMEOUT_MS"):
        Settings.from_env(
            {"MONGODB_URI": "mongodb://mongodb:27017/cruddb", "MONGODB_PING_TIMEOUT_MS": value}
        )
