from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from typing import Callable

SUPPORTED_CHANNELS = {"email", "telegram", "slack"}
SECRET_PATTERN = re.compile(
    r"(?i)(xox[baprs]-[a-z0-9-]+|https://hooks\.slack\.com/services/\S+|"
    r"bearer\s+[a-z0-9._~+/=-]+|token[=:]\S+|password[=:]\S+|secret[=:]\S+)"
)


@dataclass(frozen=True)
class NotificationEvent:
    job_name: str
    job_type: str
    level: str
    status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    summary: str


@dataclass(frozen=True)
class EffectiveNotiCLISettings:
    enabled: bool
    notification_type: str
    config: str | None
    sender: str | None
    recipient: str | None
    channel: str | None
    title: str | None
    message: str | None


@dataclass(frozen=True)
class NotificationDeliveryResult:
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""


def _noticli_section(container: dict) -> dict:
    return container.get("notifications", {}).get("noticli", {})


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if key != "failure" and value is not None:
            merged[key] = value
    return merged


def resolve_settings(cfg: dict, job: dict, event: NotificationEvent) -> EffectiveNotiCLISettings:
    global_cfg = _noticli_section(cfg)
    job_cfg = _noticli_section(job)
    enabled = bool(job_cfg.get("enabled", global_cfg.get("enabled", False)))
    notification_type = "failure" if event.status == "failed" else "success"

    values = _merge({}, global_cfg)
    if notification_type == "failure":
        values = _merge(values, global_cfg.get("failure", {}))
    values = _merge(values, job_cfg)
    if notification_type == "failure":
        values = _merge(values, job_cfg.get("failure", {}))

    title = _render(values.get("title"), event) or default_title(event)
    message = _render(values.get("message"), event) or default_message(event)

    return EffectiveNotiCLISettings(
        enabled=enabled,
        notification_type=notification_type,
        config=values.get("config"),
        sender=values.get("sender"),
        recipient=values.get("recipient"),
        channel=values.get("channel"),
        title=title,
        message=message,
    )


def validate_noticli_config(cfg: dict) -> list[str]:
    errors: list[str] = []
    _validate_section(errors, "notifications.noticli", _noticli_section(cfg))
    for job in cfg.get("jobs", []):
        name = job.get("name", "<unnamed>")
        _validate_section(errors, f"job {name} notifications.noticli", _noticli_section(job))
        if job.get("enabled", True):
            for status in ("success", "failed"):
                event = NotificationEvent(
                    job_name=name,
                    job_type=job.get("type", ""),
                    level="dump",
                    status=status,
                    started_at="",
                    ended_at="",
                    duration_seconds=0.0,
                    summary="validation",
                )
                settings = resolve_settings(cfg, job, event)
                if settings.enabled:
                    _validate_effective(errors, f"job {name} effective {settings.notification_type}", settings)
    return errors


def _validate_section(errors: list[str], label: str, section: dict) -> None:
    if not section:
        return
    if not isinstance(section, dict):
        errors.append(f"{label}: must be a table")
        return
    if "enabled" in section and not isinstance(section["enabled"], bool):
        errors.append(f"{label}: enabled must be true or false")
    _validate_values(errors, label, section)
    failure = section.get("failure")
    if failure is not None:
        if not isinstance(failure, dict):
            errors.append(f"{label}.failure: must be a table")
        else:
            _validate_values(errors, f"{label}.failure", failure)


def _validate_values(errors: list[str], label: str, values: dict) -> None:
    for key in ("config", "sender", "recipient", "channel", "title", "message"):
        if key in values and values[key] is not None and not isinstance(values[key], str):
            errors.append(f"{label}: {key} must be a string")
    if "sender" in values and isinstance(values["sender"], str) and len(values["sender"]) > 20:
        errors.append(f"{label}: sender must be at most 20 characters")
    if "channel" in values and values["channel"] not in SUPPORTED_CHANNELS:
        errors.append(f"{label}: channel must be one of {', '.join(sorted(SUPPORTED_CHANNELS))}")


def _validate_effective(errors: list[str], label: str, settings: EffectiveNotiCLISettings) -> None:
    for key in ("sender", "recipient", "channel", "title", "message"):
        if not getattr(settings, key):
            errors.append(f"{label}: missing {key}")
    if settings.channel and settings.channel not in SUPPORTED_CHANNELS:
        errors.append(f"{label}: channel must be one of {', '.join(sorted(SUPPORTED_CHANNELS))}")


def default_title(event: NotificationEvent) -> str:
    return f"vaultGFS backup {event.status}: {event.job_name}"


def default_message(event: NotificationEvent) -> str:
    return (
        f"job={event.job_name} type={event.job_type} level={event.level} "
        f"status={event.status} started={event.started_at} ended={event.ended_at} "
        f"duration_seconds={event.duration_seconds:.3f} summary={event.summary}"
    )


def _render(template: str | None, event: NotificationEvent) -> str | None:
    if not template:
        return None
    values = {
        "job_name": event.job_name,
        "job_type": event.job_type,
        "level": event.level,
        "status": event.status,
        "started_at": event.started_at,
        "ended_at": event.ended_at,
        "duration_seconds": f"{event.duration_seconds:.3f}",
        "summary": event.summary,
    }
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template


def build_command(settings: EffectiveNotiCLISettings) -> list[str]:
    missing = [
        key for key in ("sender", "recipient", "channel", "title", "message")
        if not getattr(settings, key)
    ]
    if missing:
        raise ValueError(f"missing NotiCLI notification setting(s): {', '.join(missing)}")
    cmd = ["noticli", "send"]
    if settings.config:
        cmd += ["--config", settings.config]
    cmd += [
        "--sender", settings.sender or "",
        "--recipient", settings.recipient or "",
        "--channel", settings.channel or "",
        "--title", settings.title or "",
        "--message", settings.message or "",
    ]
    return cmd


Runner = Callable[..., subprocess.CompletedProcess]


def send_notification(settings: EffectiveNotiCLISettings, runner: Runner = subprocess.run) -> NotificationDeliveryResult:
    if not settings.enabled:
        return NotificationDeliveryResult(status="skipped")
    try:
        cmd = build_command(settings)
        completed = runner(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except Exception as exc:
        return NotificationDeliveryResult(status="failed", error=redact(str(exc)))
    stdout = redact(completed.stdout or "")
    stderr = redact(completed.stderr or "")
    if completed.returncode == 0:
        return NotificationDeliveryResult(status="sent", exit_code=0, stdout=stdout, stderr=stderr)
    return NotificationDeliveryResult(
        status="failed",
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def redact(text: str) -> str:
    return SECRET_PATTERN.sub("[REDACTED]", text)


def log_delivery(job_name: str, settings: EffectiveNotiCLISettings, result: NotificationDeliveryResult) -> None:
    if result.status == "skipped":
        return
    base = (
        f"NOTIFICATION_{result.status.upper()} job={job_name} type={settings.notification_type} "
        f"channel={settings.channel or '-'} recipient={settings.recipient or '-'}"
    )
    if result.exit_code is not None:
        base += f" exit_code={result.exit_code}"
    details = " ".join(
        part for part in [
            f"stdout={result.stdout.strip()}" if result.stdout.strip() else "",
            f"stderr={result.stderr.strip()}" if result.stderr.strip() else "",
            f"error={result.error.strip()}" if result.error.strip() else "",
        ] if part
    )
    print(f"{base} {details}".rstrip(), flush=True)
