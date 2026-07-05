# Requirements Checklist: NotiCLI Backup Notifications

**Purpose**: Validate clarity, completeness, consistency and traceability of requirements before implementation tasks.
**Created**: 2026-07-04
**Feature**: [spec.md](../spec.md)

## Completeness

- [x] CHK001 - Are global enablement and global settings documented for NotiCLI notifications? [Completeness, Spec FR-001, FR-002] {auto}
- [x] CHK002 - Are per-job overrides and explicit per-job disablement documented? [Completeness, Spec FR-003, FR-004] {auto}
- [x] CHK003 - Are default and failure-specific notification settings both documented? [Completeness, Spec FR-006, FR-007] {auto}
- [x] CHK004 - Are required NotiCLI parameters documented without requiring an embedded dependency? [Completeness, Spec FR-008, FR-024; Contract §Arguments] {auto}
- [x] CHK005 - Is documentation/reference configuration work captured as a requirement? [Completeness, Spec FR-021, FR-022] {auto}

## Clarity

- [x] CHK006 - Is configuration precedence specified in a deterministic order? [Clarity, Spec FR-005] {auto}
- [x] CHK007 - Is the backup outcome rule for notification failures unambiguous? [Clarity, Spec FR-013, FR-014] {auto}
- [x] CHK008 - Is the configuration format clarified as TOML instead of leaving `application.properties` unresolved? [Clarity, Spec FR-022; Research Decision 1] {auto}
- [x] CHK009 - Are validation expectations for incomplete notification settings stated? [Clarity, Spec FR-018; Plan §Convenções de Borda] {auto}

## Consistency

- [x] CHK010 - Do spec and plan agree that NotiCLI is called as an external executable from PATH? [Consistency, Spec FR-024; Plan §Summary; Research Decision 2] {auto}
- [x] CHK011 - Do spec and plan agree that notification failure is logged but never changes backup status? [Consistency, Spec FR-013-FR-017; Research Decision 3] {auto}
- [x] CHK012 - Do spec and plan align with existing vaultGFS TOML configuration conventions? [Consistency, Spec FR-022; Plan §Technical Context; Research Decision 1] {auto}

## Scenario Coverage

- [x] CHK013 - Are success notification scenarios covered? [Coverage, User Story 1; Quickstart Scenario 1] {auto}
- [x] CHK014 - Are per-job override scenarios covered? [Coverage, User Story 2; Quickstart Scenario 2] {auto}
- [x] CHK015 - Are failure-specific notification scenarios covered? [Coverage, User Story 3; Quickstart Scenario 3] {auto}
- [x] CHK016 - Are notification delivery failure scenarios covered? [Coverage, User Story 4; Quickstart Scenario 4] {auto}
- [x] CHK017 - Are disabled notification scenarios covered? [Coverage, User Story 1 Scenario 2; Quickstart Scenario 5] {auto}

## Edge Cases And Dependencies

- [x] CHK018 - Is missing NotiCLI on PATH covered as an edge case? [Edge Case, Spec Edge Cases; Contract §Expected Results] {auto}
- [x] CHK019 - Are non-zero NotiCLI exit codes covered? [Edge Case, Spec Edge Cases; Contract §Expected Results] {auto}
- [x] CHK020 - Are secret-redaction expectations covered for notification diagnostics? [Security, Spec FR-016; Contract §Logging Contract] {auto}
- [x] CHK021 - Are duplicate-notification prevention expectations documented? [Completeness, Spec FR-019] {auto}

## Measurability

- [x] CHK022 - Are success criteria objectively verifiable? [Measurability, Spec SC-001-SC-006] {auto}
- [x] CHK023 - Do success criteria cover both positive delivery and failure isolation? [Measurability, Spec SC-001-SC-003] {auto}
- [x] CHK024 - Can acceptance scenarios be translated into tests without additional product decisions? [Traceability, User Stories 1-4; Quickstart Scenarios 1-5] {auto}

## Notes

- No open `[Gap]`, `[Ambiguity]` or `[Conflict]` markers were found.
- No `{humano}` decisions are required by this checklist before task creation.
