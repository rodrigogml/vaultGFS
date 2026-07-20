from __future__ import annotations

import pytest

from vaultgfs import cli_backup
from vaultgfs.notification import NotificationDeliveryResult


class DummySlot:
    def __init__(self, cfg):
        self.cfg = cfg

    def acquire(self):
        return 0

    def release(self):
        pass


def base_cfg():
    return {
        "defaults": {},
        "notifications": {
            "noticli": {
                "enabled": True,
                "sender": "vaultGFS",
                "category": "SUCCESS",
                "title": "Backup {status}",
            }
        },
        "jobs": [
            {
                "name": "files",
                "enabled": True,
                "type": "filesystem-gfs",
                "source": "/data",
                "destination": "/backup",
                "schedule_full": "0 1 * * *",
                "schedule_diff": "0 1 * * 0",
                "schedule_inc": "0 1 * * *",
            }
        ],
    }


def test_cli_sends_notification_after_success_without_changing_return(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(cli_backup, "load_config", lambda path: base_cfg())
    monkeypatch.setattr(cli_backup, "BackupSlot", DummySlot)
    monkeypatch.setattr(cli_backup, "run_filesystem_job", lambda cfg, job, level: 0)

    def fake_send(settings):
        sent.append(settings)
        return NotificationDeliveryResult(status="sent", exit_code=0)

    monkeypatch.setattr(cli_backup, "send_notification", fake_send)

    rc = cli_backup.main(["--config", "ignored.toml", "--job", "files", "--level", "full"])

    assert rc == 0
    assert len(sent) == 1
    assert sent[0].notification_type == "success"
    assert "NOTIFICATION_SENT job=files" in capsys.readouterr().out


def test_cli_preserves_backup_success_when_notification_fails(monkeypatch, capsys):
    monkeypatch.setattr(cli_backup, "load_config", lambda path: base_cfg())
    monkeypatch.setattr(cli_backup, "BackupSlot", DummySlot)
    monkeypatch.setattr(cli_backup, "run_filesystem_job", lambda cfg, job, level: 0)
    monkeypatch.setattr(
        cli_backup,
        "send_notification",
        lambda settings: NotificationDeliveryResult(status="failed", exit_code=6, stderr="delivery failed"),
    )

    rc = cli_backup.main(["--config", "ignored.toml", "--job", "files", "--level", "full"])

    assert rc == 0
    output = capsys.readouterr().out
    assert "NOTIFICATION_FAILED job=files type=success category=SUCCESS priority=- exit_code=6" in output
    assert "RUN_END job=files" in output


def test_cli_does_not_notify_disabled_job(monkeypatch):
    cfg = base_cfg()
    cfg["jobs"][0]["enabled"] = False
    sent = []
    monkeypatch.setattr(cli_backup, "load_config", lambda path: cfg)
    monkeypatch.setattr(cli_backup, "BackupSlot", DummySlot)
    monkeypatch.setattr(cli_backup, "send_notification", lambda settings: sent.append(settings))

    rc = cli_backup.main(["--config", "ignored.toml", "--job", "files", "--level", "full"])

    assert rc == 0
    assert sent == []


def test_cli_sends_failure_notification_when_backup_raises(monkeypatch):
    sent = []
    monkeypatch.setattr(cli_backup, "load_config", lambda path: base_cfg())
    monkeypatch.setattr(cli_backup, "BackupSlot", DummySlot)

    def fail_backup(cfg, job, level):
        raise RuntimeError("archive failed")

    def fake_send(settings):
        sent.append(settings)
        return NotificationDeliveryResult(status="sent", exit_code=0)

    monkeypatch.setattr(cli_backup, "run_filesystem_job", fail_backup)
    monkeypatch.setattr(cli_backup, "send_notification", fake_send)

    with pytest.raises(RuntimeError, match="archive failed"):
        cli_backup.main(["--config", "ignored.toml", "--job", "files", "--level", "full"])

    assert len(sent) == 1
    assert sent[0].notification_type == "failure"
    assert sent[0].message and "archive failed" in sent[0].message


def test_cli_runs_pfsense_job_and_sends_notification(monkeypatch):
    cfg = base_cfg()
    cfg["jobs"] = [
        {
            "name": "pfsense",
            "enabled": True,
            "type": "pfsense-config",
            "base_url": "https://example",
            "username": "vaultGFS",
            "password": "secret",
            "destination": "/backup/pfsense",
            "schedule": "0 4 * * *",
        }
    ]
    sent = []
    called = []
    monkeypatch.setattr(cli_backup, "load_config", lambda path: cfg)
    monkeypatch.setattr(cli_backup, "BackupSlot", DummySlot)
    monkeypatch.setattr(cli_backup, "run_pfsense_job", lambda cfg, job: called.append(job["name"]) or 0)
    monkeypatch.setattr(cli_backup, "send_notification", lambda settings: sent.append(settings) or NotificationDeliveryResult(status="sent", exit_code=0))

    rc = cli_backup.main(["--config", "ignored.toml", "--job", "pfsense"])

    assert rc == 0
    assert called == ["pfsense"]
    assert sent[0].notification_type == "success"
