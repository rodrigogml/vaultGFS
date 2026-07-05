from __future__ import annotations

from vaultgfs.config import load_config, validate_config


def test_load_config_defaults_jobs_and_validates_noticli(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        """
[defaults]
catalog = "/tmp/catalog.db"

[notifications.noticli]
enabled = true
sender = "vaultGFS"
recipient = "ops"
channel = "email"
title = "Backup {status}"

[[jobs]]
name = "mysql"
type = "mysql-dump"
schemas = ["app"]
destination = "/backup/mysql"
schedule = "0 1 * * *"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(config)

    assert cfg["jobs"][0]["enabled"] is True
    assert cfg["jobs"][0]["skip_if_unchanged"] is False
    assert validate_config(cfg) == []


def test_validate_config_reports_invalid_noticli_channel():
    cfg = {
        "defaults": {},
        "notifications": {
            "noticli": {
                "enabled": True,
                "sender": "vaultGFS",
                "recipient": "ops",
                "channel": "sms",
                "title": "Backup",
            }
        },
        "jobs": [
            {
                "name": "mysql",
                "enabled": True,
                "type": "mysql-dump",
                "schemas": ["app"],
                "destination": "/backup/mysql",
                "schedule": "0 1 * * *",
            }
        ],
    }

    errors = validate_config(cfg)

    assert "notifications.noticli: channel must be one of email, slack, telegram" in errors
    assert "job mysql effective success: channel must be one of email, slack, telegram" in errors


def test_validate_config_allows_partial_job_override_from_global_defaults():
    cfg = {
        "defaults": {},
        "notifications": {
            "noticli": {
                "enabled": False,
                "sender": "vaultGFS",
                "recipient": "ops",
                "channel": "email",
                "title": "Backup",
            }
        },
        "jobs": [
            {
                "name": "mysql",
                "enabled": True,
                "type": "mysql-dump",
                "schemas": ["app"],
                "destination": "/backup/mysql",
                "schedule": "0 1 * * *",
                "notifications": {"noticli": {"enabled": True, "recipient": "db-ops"}},
            }
        ],
    }

    assert validate_config(cfg) == []
