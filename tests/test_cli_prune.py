from __future__ import annotations

import pytest

from vaultgfs import cli_prune
from vaultgfs.notification import NotificationDeliveryResult


def config():
    return {
        "defaults": {},
        "notifications": {
            "noticli": {
                "enabled": True,
                "sender": "vaultGFS",
                "category": "SUCCESS",
                "title": "Prune {status}",
            }
        },
        "jobs": [],
    }


class DummyDb:
    pass


def test_prune_sends_success_notification(monkeypatch):
    sent = []
    monkeypatch.setattr(cli_prune, "load_config", lambda path: config())
    monkeypatch.setattr(cli_prune, "catalog", type("DummyCatalog", (), {"connect": lambda path: DummyDb()}))
    monkeypatch.setattr(cli_prune, "send_notification", lambda settings: sent.append(settings) or NotificationDeliveryResult(status="sent", exit_code=0))

    rc = cli_prune.main(["--config", "ignored.toml", "--apply"])

    assert rc == 0
    assert len(sent) == 1
    assert sent[0].notification_type == "success"
    assert sent[0].message and "mode=APPLY candidates=0 pruned=0 skipped=0" in sent[0].message


def test_prune_sends_failure_notification(monkeypatch):
    sent = []
    monkeypatch.setattr(cli_prune, "load_config", lambda path: config())
    monkeypatch.setattr(cli_prune, "catalog", type("DummyCatalog", (), {"connect": lambda path: (_ for _ in ()).throw(RuntimeError("catalog failed"))}))
    monkeypatch.setattr(cli_prune, "send_notification", lambda settings: sent.append(settings) or NotificationDeliveryResult(status="sent", exit_code=0))

    with pytest.raises(RuntimeError, match="catalog failed"):
        cli_prune.main(["--config", "ignored.toml", "--apply"])

    assert len(sent) == 1
    assert sent[0].notification_type == "failure"
    assert sent[0].message and "catalog failed" in sent[0].message
