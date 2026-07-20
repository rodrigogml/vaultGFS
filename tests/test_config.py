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
category = "SUCCESS"
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


def test_validate_config_reports_invalid_noticli_priority():
    cfg = {
        "defaults": {},
        "notifications": {
            "noticli": {
                "enabled": True,
                "sender": "vaultGFS",
                "priority": "URGENT",
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

    assert "notifications.noticli: priority must be one of HIGH, LOW, NORMAL" in errors
    assert "job mysql effective success: priority must be one of HIGH, LOW, NORMAL" in errors


def test_validate_config_allows_partial_job_override_from_global_defaults():
    cfg = {
        "defaults": {},
        "notifications": {
            "noticli": {
                "enabled": False,
                "sender": "vaultGFS",
                "category": "SUCCESS",
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
                "notifications": {"noticli": {"enabled": True, "category": "DB"}},
            }
        ],
    }

    assert validate_config(cfg) == []


def test_validate_config_reports_invalid_retention_counts():
    cfg = {
        "defaults": {"retention": {"filesystem_gfs": {"keep_full": -1}}},
        "jobs": [
            {
                "name": "mysql",
                "enabled": True,
                "type": "mysql-dump",
                "schemas": ["app"],
                "destination": "/backup/mysql",
                "schedule": "0 1 * * *",
                "retention": {"keep_daily": "14"},
            }
        ],
    }

    errors = validate_config(cfg)

    assert "defaults.retention.filesystem_gfs: keep_full must be a non-negative integer" in errors
    assert "job mysql retention: keep_daily must be a non-negative integer" in errors


def test_validate_config_accepts_pfsense_job():
    cfg = {
        "defaults": {},
        "jobs": [
            {
                "name": "pfsense",
                "enabled": True,
                "type": "pfsense-config",
                "base_url": "https://192.168.1.1",
                "username": "vaultGFS",
                "password": "secret",
                "verify_tls": False,
                "destination": "/backup/pfsense",
                "schedule": "0 4 * * *",
            }
        ],
    }

    assert validate_config(cfg) == []


def test_validate_config_reports_invalid_pfsense_job():
    cfg = {
        "defaults": {},
        "jobs": [
            {
                "name": "pfsense",
                "enabled": True,
                "type": "pfsense-config",
                "base_url": "https://192.168.1.1",
                "verify_tls": "no",
                "destination": "/backup/pfsense",
                "schedule": "0 4 * * *",
            }
        ],
    }

    errors = validate_config(cfg)

    assert "job pfsense: missing username" in errors
    assert "job pfsense: missing password" in errors
    assert "job pfsense: verify_tls must be true or false" in errors
