from __future__ import annotations

import subprocess

from vaultgfs.notification import (
    EffectiveNotiCLISettings,
    NotificationEvent,
    build_command,
    default_message,
    redact,
    resolve_settings,
    send_notification,
)


def event(status: str = "success") -> NotificationEvent:
    return NotificationEvent(
        job_name="files",
        job_type="filesystem-gfs",
        level="full",
        status=status,
        started_at="2026-07-04T10:00:00",
        ended_at="2026-07-04T10:01:00",
        duration_seconds=60.0,
        summary="ok",
    )


def test_resolve_settings_uses_job_failure_overrides_before_global_defaults():
    cfg = {
        "notifications": {
            "noticli": {
                "enabled": True,
                "sender": "vaultGFS",
                "category": "SUCCESS",
                "title": "Backup {status}",
                "message": "Job {job_name} {status}",
                "failure": {"title": "Global failure"},
            }
        }
    }
    job = {
        "name": "files",
        "type": "filesystem-gfs",
        "notifications": {
            "noticli": {
                "category": "FAIL",
                "failure": {"sender": "vaultAlert", "title": "Job {job_name} failed"},
            }
        },
    }

    settings = resolve_settings(cfg, job, event("failed"))

    assert settings.enabled is True
    assert settings.notification_type == "failure"
    assert settings.sender == "vaultAlert"
    assert settings.category == "FAIL"
    assert settings.priority == "HIGH"
    assert settings.title == "Job files failed"
    assert settings.message == "Job files failed"


def test_build_command_omits_optional_config_when_not_configured():
    settings = EffectiveNotiCLISettings(
        enabled=True,
        notification_type="success",
        config=None,
        sender="vaultGFS",
        category="SUCCESS",
        priority=None,
        title="Backup ok",
        message="Done",
    )

    assert build_command(settings) == [
        "noticli",
        "send",
        "--sender",
        "vaultGFS",
        "--category",
        "SUCCESS",
        "--title",
        "Backup ok",
        "--message",
        "Done",
    ]


def test_default_success_message_uses_plain_text_multiline_layout():
    assert default_message(event()) == (
        "Backup concluido\n"
        "\n"
        "- Job: files\n"
        "- Tipo: filesystem-gfs\n"
        "- Nivel: full\n"
        "- Status: success\n"
        "- Inicio: 2026-07-04T10:00:00\n"
        "- Fim: 2026-07-04T10:01:00\n"
        "- Duracao: 60.000s\n"
        "- Resumo: ok"
    )


def test_default_failure_message_labels_summary_as_error():
    assert default_message(event("failed")) == (
        "Backup falhou\n"
        "\n"
        "- Job: files\n"
        "- Tipo: filesystem-gfs\n"
        "- Nivel: full\n"
        "- Status: failed\n"
        "- Inicio: 2026-07-04T10:00:00\n"
        "- Fim: 2026-07-04T10:01:00\n"
        "- Duracao: 60.000s\n"
        "- Erro: ok"
    )


def test_send_notification_returns_failed_result_without_raising_on_nonzero_exit():
    settings = EffectiveNotiCLISettings(
        enabled=True,
        notification_type="failure",
        config="/opt/noticli.json",
        sender="vaultGFS",
        category="FAIL",
        priority="HIGH",
        title="Backup failed",
        message="Failure",
    )

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 6, stdout="", stderr="token=abc delivery failed")

    result = send_notification(settings, runner=runner)

    assert result.status == "failed"
    assert result.exit_code == 6
    assert "token=abc" not in result.stderr
    assert "[REDACTED]" in result.stderr


def test_send_notification_returns_failed_result_when_executable_is_missing():
    settings = EffectiveNotiCLISettings(
        enabled=True,
        notification_type="success",
        config=None,
        sender="vaultGFS",
        category="SUCCESS",
        priority=None,
        title="Backup ok",
        message="Done",
    )

    def runner(*args, **kwargs):
        raise FileNotFoundError("noticli")

    result = send_notification(settings, runner=runner)

    assert result.status == "failed"
    assert result.exit_code is None
    assert "noticli" in result.error


def test_redact_common_secret_patterns():
    assert redact("password=abc token=def bearer xyz") == "[REDACTED] [REDACTED] [REDACTED]"
