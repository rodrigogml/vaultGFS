# Feature Specification: NotiCLI Backup Notifications

**Feature**: `noticli-backup-notifications`
**Created**: 2026-07-04
**Status**: Draft

## User Scenarios & Testing

### User Story 1 - Receive Backup Result Notifications (Priority: P1)

As an operator responsible for backup monitoring, I want vaultGFS to notify me after each completed backup when notifications are enabled, so that I can confirm backup outcomes without manually inspecting logs or the catalog after every run.

**Why this priority**: This is the minimum useful capability for the feature. A configured operator receives execution status for existing backup jobs without changing the backup workflow.

**Independent Test**: Enable NotiCLI notifications globally, execute one successful backup job, and verify that exactly one notification is requested with the configured recipient, channel, sender, title and message content.

**Acceptance Scenarios**:

1. **Given** global NotiCLI notifications are enabled and configured, **When** a backup finishes successfully, **Then** vaultGFS requests a success notification containing the job identity, backup status and relevant execution summary.
2. **Given** global NotiCLI notifications are disabled, **When** any backup finishes, **Then** vaultGFS does not request a NotiCLI notification.
3. **Given** NotiCLI notifications are enabled, **When** the backup run has no optional attachment or external report, **Then** the notification still sends the textual execution summary.

---

### User Story 2 - Override Notification Settings Per Job (Priority: P2)

As an operator managing multiple backup jobs, I want each job to override the global NotiCLI notification settings when needed, so that different backups can notify different recipients, channels or senders while still sharing sensible defaults.

**Why this priority**: Multi-job installations commonly route database, filesystem and critical job alerts differently. Per-job overrides make the feature useful without duplicating every setting for every job.

**Independent Test**: Configure global NotiCLI notification defaults and override only selected notification fields in one job, execute that job, and verify that overridden fields come from the job while omitted fields come from the global configuration.

**Acceptance Scenarios**:

1. **Given** global notification settings define recipient, channel, sender, title and message defaults, **When** a job defines only a different recipient, **Then** the notification uses the job recipient and the remaining global defaults.
2. **Given** two jobs with different notification overrides, **When** both jobs complete, **Then** each notification uses the effective settings for its own job.
3. **Given** a job disables NotiCLI notifications explicitly, **When** that job completes, **Then** vaultGFS does not request a notification for that job even if global notifications are enabled.

---

### User Story 3 - Distinguish Failure Notifications (Priority: P3)

As an operator, I want failed backups to use failure-specific notification settings when configured, so that I can filter or prioritize failure alerts separately from routine success messages.

**Why this priority**: Failure alerts have higher operational urgency than success notifications and may require different titles, sender names, recipients or channels.

**Independent Test**: Configure default notification settings and failure-specific settings, execute a backup that fails, and verify that the failure notification uses the failure-specific values where present and falls back to default values where absent.

**Acceptance Scenarios**:

1. **Given** default and failure-specific notification settings are configured, **When** a backup fails, **Then** vaultGFS requests a failure notification using failure-specific values before falling back to default values.
2. **Given** only default notification settings are configured, **When** a backup fails, **Then** vaultGFS requests a failure notification using the default settings with failure status in the message.
3. **Given** a backup succeeds, **When** failure-specific settings exist, **Then** vaultGFS does not use failure-specific values for the success notification.

---

### User Story 4 - Preserve Backup Outcome When Notification Fails (Priority: P4)

As an operator, I want notification delivery failures to be logged without changing the backup result, so that vaultGFS remains a reliable backup system even when the external notification tool is unavailable or misconfigured.

**Why this priority**: Notification is an operational side effect. A failure in that side effect must be diagnosable, but it must not corrupt backup status or stop the backup workflow.

**Independent Test**: Configure NotiCLI notifications with an invalid recipient or missing executable, execute a backup that otherwise succeeds, and verify that the backup remains successful while vaultGFS logs the notification failure with diagnostic context.

**Acceptance Scenarios**:

1. **Given** a backup completes successfully and the NotiCLI notification request fails, **When** vaultGFS records the final backup result, **Then** the backup remains successful.
2. **Given** a backup fails and the failure notification also fails, **When** vaultGFS records diagnostics, **Then** the original backup failure remains the backup result and the notification failure is logged as additional diagnostic information.
3. **Given** NotiCLI returns a non-success result, **When** vaultGFS logs the notification failure, **Then** the log includes enough context to diagnose the notification problem without exposing configured secrets.

### Edge Cases

- NotiCLI is not available on the system PATH while notifications are enabled.
- NotiCLI returns a non-zero exit code for invalid input, missing configuration, invalid configuration, attachment errors or delivery failure.
- The effective notification configuration is incomplete for an enabled notification.
- A job overrides only failure settings and inherits default settings for success notifications.
- A job overrides only some failure fields and inherits the remaining fields from the effective default notification settings.
- The configured sender exceeds the NotiCLI sender limit.
- The configured channel does not match a channel supported by NotiCLI.
- Notification message content contains paths, job names or error text that may be long.
- Backup execution is skipped because no filesystem changes are detected.
- Notification failure diagnostics may include command outcome details but must not expose secrets, tokens, passwords or webhook URLs.

## Requirements

### Functional Requirements

- **FR-001**: vaultGFS MUST support an optional global NotiCLI notification configuration for backup execution results.
- **FR-002**: vaultGFS MUST allow NotiCLI notifications to be enabled or disabled globally.
- **FR-003**: vaultGFS MUST allow each job to override the global NotiCLI notification configuration.
- **FR-004**: vaultGFS MUST allow each job to explicitly disable NotiCLI notifications even when global notifications are enabled.
- **FR-005**: vaultGFS MUST derive effective notification settings using this precedence: job failure-specific settings for failed backups, job default settings, global failure-specific settings for failed backups, global default settings.
- **FR-006**: vaultGFS MUST support default notification settings that apply to all notification outcomes.
- **FR-007**: vaultGFS MUST support failure-specific notification settings that override default notification settings only when the backup outcome is failed.
- **FR-008**: vaultGFS MUST support the NotiCLI parameters required to identify notification configuration, sender, recipient, channel, title and message.
- **FR-009**: vaultGFS MUST treat the NotiCLI configuration path as optional when the operator chooses to rely on the NotiCLI default configuration.
- **FR-010**: vaultGFS MUST include backup execution context in notification messages, including job name, job type, requested level when applicable, final status, start time, end time or duration, and a concise result summary.
- **FR-011**: vaultGFS MUST request a success notification after a successful backup when notifications are enabled and effective settings are complete.
- **FR-012**: vaultGFS MUST request a failure notification after a failed backup when notifications are enabled and effective settings are complete.
- **FR-013**: vaultGFS MUST NOT interrupt, roll back or change the backup result when NotiCLI notification delivery fails.
- **FR-014**: vaultGFS MUST NOT mark a successful backup as failed because NotiCLI notification delivery failed.
- **FR-015**: vaultGFS MUST log NotiCLI notification failures in vaultGFS logs with diagnostic details including job name, notification type, effective channel, effective recipient, exit code when available and diagnostic output when available.
- **FR-016**: vaultGFS MUST redact or avoid logging secrets and credential-like values when recording NotiCLI notification diagnostics.
- **FR-017**: vaultGFS MUST make notification delivery outcome visible in logs independently from backup execution outcome.
- **FR-018**: vaultGFS MUST validate enabled NotiCLI notification settings sufficiently to report incomplete or unsupported settings before or during backup execution.
- **FR-019**: vaultGFS MUST avoid sending duplicate notifications for a single backup execution result.
- **FR-020**: vaultGFS MUST support the same notification configuration structure globally and per job, including default and failure-specific values.
- **FR-021**: vaultGFS MUST document the NotiCLI notification configuration model in the project documentation and reference configuration.
- **FR-022**: vaultGFS MUST define NotiCLI notification settings using the current vaultGFS TOML configuration model, including the versioned reference configuration and the operator-maintained runtime configuration.
- **FR-023**: vaultGFS MUST not introduce a new scheduler or daemon for notifications; notification requests are tied to existing backup execution completion.
- **FR-024**: vaultGFS MUST integrate with NotiCLI as an external executable available on the system PATH and MUST NOT require an embedded NotiCLI library or package dependency.

### Key Entities

- **NotiCLI Notification Settings**: Operator-defined settings that control whether notifications are enabled and which recipient, channel, sender, title, message template and optional NotiCLI configuration path are used.
- **Effective Notification Settings**: The resolved settings for one backup execution after applying global defaults, global failure overrides, job defaults and job failure overrides.
- **Backup Notification Event**: A notification request produced from one completed backup execution, including the backup identity, final status and execution summary.
- **Notification Delivery Result**: The observed result of requesting delivery through NotiCLI, including success or failure diagnostics used for vaultGFS logging.

## Success Criteria

### Measurable Outcomes

- **SC-001**: In a configured environment, 100% of completed backup executions with enabled and complete notification settings produce exactly one notification request.
- **SC-002**: 100% of backup executions keep their original final status when notification delivery fails.
- **SC-003**: 100% of NotiCLI notification failures are represented in vaultGFS logs with job identity, notification type and failure category or exit code when available.
- **SC-004**: Operators can configure a global notification default and a per-job override for a job without duplicating every notification field.
- **SC-005**: Operators can distinguish failed backup notifications from successful backup notifications by configuring at least one different failure-specific field such as title, sender, recipient or channel.
- **SC-006**: Documentation and reference configuration allow an operator to enable a basic NotiCLI notification flow without reading vaultGFS source code.
