# Implementation Plan: NotiCLI Backup Notifications

**Feature**: `noticli-backup-notifications` | **Date**: 2026-07-04 | **Spec**: [spec.md](./spec.md)

## Summary

Add optional NotiCLI notifications to the existing `vaultgfs-backup` lifecycle. The implementation will keep backup execution as the source of truth for job status, resolve notification settings from the current TOML configuration model, call `noticli send` as an external executable from PATH and log notification delivery failures without changing backup results.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Python standard library; external runtime tools already used by vaultGFS; NotiCLI as PATH executable
**Storage**: Existing SQLite catalog for backup runs; no new persistent storage for notifications
**Testing**: Add `pytest` for unit and CLI behavior tests
**Target Platform**: Linux production runtime, with NotiCLI invocation kept OS-neutral at the command boundary
**Project Type**: CLI utility packaged as a Python distribution
**Performance Goals**: Notification adds one bounded external process invocation after backup completion when enabled
**Constraints**: No embedded NotiCLI package dependency; notification failure must not alter backup status
**Scale/Scope**: Multiple independent backup jobs using global defaults and per-job overrides

## Constitution Check

*GATE: Deve passar antes do Phase 0. Rechecar após Phase 1.*

No constitution found in `docs/constitution.md`.

| Princípio | Status | Notas |
|-----------|--------|-------|
| Project constitution | N/A | No constitution file exists in this repository. |

## Project Structure

### Documentation (this feature)

```text
docs/specs/noticli-backup-notifications/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── noticli-invocation.md
```

### Source Code (repository root)

```text
config.toml.model
docs/
├── requirements.md
└── specs/noticli-backup-notifications/
src/vaultgfs/
├── cli_backup.py
├── config.py
├── fs_backup.py
├── mysql_dump.py
└── notification.py       # planned new module
tests/
├── test_config.py        # planned config validation coverage
├── test_notification.py  # planned notification resolution and subprocess coverage
└── test_cli_backup.py    # planned lifecycle notification behavior coverage
```

**Structure Decision**: Add NotiCLI-specific behavior in a new `src/vaultgfs/notification.py` module, wire it from `cli_backup.py` after job execution resolves a final status, and keep `fs_backup.py` and `mysql_dump.py` focused on backup mechanics.

## Convenções de Borda

| Camada | Case style | Validação | Fonte da verdade |
|--------|------------|-----------|------------------|
| TOML config keys | snake_case | `validate_config` plus notification settings validation | `config.toml.model`, `src/vaultgfs/config.py` |
| Python settings dicts | snake_case | Unit tests and module-level validation | `src/vaultgfs/notification.py` |
| External CLI arguments | kebab-case flags | Command construction tests | `docs/specs/noticli-backup-notifications/contracts/noticli-invocation.md` |
| Log fields | snake_case key-value text | CLI behavior tests | Existing vaultGFS log style in `cli_backup.py` |

**Mapper layer (config -> command)**: `src/vaultgfs/notification.py` resolves TOML dictionaries into effective notification settings and maps them to `noticli send` arguments.

**Validação de schema**: TOML configuration is validated during `validate_config`; runtime notification send performs defensive validation before invoking NotiCLI.

## Complexity Tracking

No constitution violations or exceptional complexity identified.
