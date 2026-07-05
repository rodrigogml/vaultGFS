# Data Model: NotiCLI Backup Notifications

## Entity: NotiCLI Notification Settings

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| enabled | boolean | Optional | Controls whether notifications are active at global or job scope. |
| config | path string | Optional | Passed to NotiCLI when set; omitted to use NotiCLI defaults. |
| sender | string | Required when effective notification is enabled | NotiCLI sender identifier, up to the NotiCLI limit. |
| recipient | string | Required when effective notification is enabled | Recipient key defined in the NotiCLI configuration. |
| channel | enum string | Required when effective notification is enabled | Expected values are NotiCLI channels such as `email`, `telegram` or `slack`. |
| title | string | Required when effective notification is enabled | Notification title or subject. |
| message | string | Optional | Message template or static text; if omitted, vaultGFS uses a default execution summary. |

### Relationships

- Global settings define defaults for all jobs.
- Job settings override global settings field by field.
- Failure settings override default settings only for failed backup outcomes.

### State Transitions

```text
not_configured -> disabled -> enabled -> effective_for_run
```

## Entity: Effective Notification Settings

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| enabled | boolean | Required | Final decision after resolving global and job configuration. |
| notification_type | enum | Required | `success`, `failure` or another final backup outcome mapped by vaultGFS. |
| config | path string | Optional | Final NotiCLI config argument. |
| sender | string | Required if enabled | Final sender value after precedence resolution. |
| recipient | string | Required if enabled | Final recipient value after precedence resolution. |
| channel | enum string | Required if enabled | Final channel value after precedence resolution. |
| title | string | Required if enabled | Final title value after precedence resolution. |
| message | string | Required if enabled | Rendered message sent to NotiCLI. |

### Relationships

- Derived from NotiCLI Notification Settings and one Backup Notification Event.
- Used to build exactly one NotiCLI command per notified backup execution.

## Entity: Backup Notification Event

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| job_name | string | Required | Name of the completed job. |
| job_type | string | Required | Existing vaultGFS job type. |
| level | string | Optional | Filesystem backup level or `dump` for MySQL jobs. |
| status | enum string | Required | Final backup status such as `success`, `failed` or `skipped`. |
| started_at | timestamp string | Required | Run start boundary from the CLI lifecycle. |
| ended_at | timestamp string | Required | Run end boundary from the CLI lifecycle. |
| duration_seconds | decimal | Required | Runtime duration after acquiring a backup slot. |
| summary | string | Required | Concise outcome summary for message rendering. |

### Relationships

- Produced once per `vaultgfs-backup` execution after the job result is known.
- Consumed by notification settings resolution and message rendering.

## Entity: Notification Delivery Result

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| status | enum string | Required | `sent`, `skipped` or `failed`. |
| exit_code | integer | Optional | NotiCLI process return code when a process was started. |
| stdout | string | Optional | Captured process output for diagnostics. |
| stderr | string | Optional | Captured process diagnostics. |
| error | string | Optional | Local execution error such as executable not found. |

### Relationships

- Logged independently from backup run status.
- Never changes the backup result.
