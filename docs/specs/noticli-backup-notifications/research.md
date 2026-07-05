# Research: NotiCLI Backup Notifications

Documento produzido no Phase 0 do plan. Resolve decisões técnicas antes do design.

## Decision 1: Configuration Format

**Decision**: Use the existing vaultGFS TOML configuration model, with global settings under `defaults` and optional job-level overrides inside each `[[jobs]]` block.

**Rationale**: The project currently loads `/opt/vaultGFS/config.toml` with `tomllib`, publishes `config.toml.model` as the reference configuration and documents TOML as the runtime configuration format. Introducing `application.properties` would create a second configuration model without functional benefit.

**Alternatives considered**: Add `application.properties`; rejected because vaultGFS is not a Spring Boot project and the current Python CLI has a stable TOML convention.

## Decision 2: NotiCLI Integration Boundary

**Decision**: Invoke `noticli send` as an external executable resolved from the system PATH.

**Rationale**: The feature requirement explicitly avoids adding a library dependency. A subprocess boundary also keeps vaultGFS independent from NotiCLI release packaging and operating system binary names, as long as the executable is available as `noticli`.

**Alternatives considered**: Vendor a Python integration package or call NotiCLI internals; rejected because that would add coupling and violate the no-dependency requirement.

## Decision 3: Notification Failure Handling

**Decision**: Treat notification delivery failure as a logged side effect failure, never as a backup failure.

**Rationale**: Backup correctness must remain determined by the backup job outcome. Operators still need detailed notification diagnostics, so vaultGFS logs job name, notification type, effective channel, effective recipient, exit code and diagnostic output when available.

**Alternatives considered**: Fail the backup when notification fails; rejected because it would make an external alerting problem corrupt backup status.

## Decision 4: Implementation Shape

**Decision**: Add a focused notification module that resolves effective settings, builds the NotiCLI command and sends notifications after job execution completes in `vaultgfs-backup`.

**Rationale**: `cli_backup.py` already owns backup lifecycle boundaries (`QUEUE_INFO`, `RUN_START`, `RUN_END`) and receives the final return code. A separate module keeps subprocess invocation and configuration resolution testable without spreading NotiCLI-specific behavior through filesystem and MySQL backup modules.

**Alternatives considered**: Add notification calls inside each job implementation; rejected because it would duplicate logic and make cross-job behavior harder to keep consistent.

## Decision 5: Test Strategy

**Decision**: Unit-test configuration resolution, command construction, validation and failure handling with test doubles for subprocess execution; cover CLI behavior with focused tests against `main(argv)`.

**Rationale**: The repository currently has no test suite, but the feature has enough logic to justify adding `pytest`-based tests. Tests should not depend on a real NotiCLI binary or real backup artifacts for notification behavior.

**Alternatives considered**: Manual validation only; rejected because precedence rules and non-failing notification errors are regression-prone.
