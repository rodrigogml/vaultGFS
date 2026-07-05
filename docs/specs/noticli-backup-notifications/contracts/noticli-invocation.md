# Contracts: NotiCLI Invocation

## Command: `noticli send`

**Type**: External CLI process
**Caller**: `vaultgfs-backup`
**Executable Resolution**: `noticli` from the system PATH

### Arguments

| Argument | Required | Source | Validation |
|----------|----------|--------|------------|
| `send` | yes | Constant | Always the first NotiCLI subcommand. |
| `--config <path>` | no | Effective notification settings | Included only when configured. |
| `--sender <text>` | yes | Effective notification settings | Non-empty; must respect NotiCLI sender constraints. |
| `--recipient <id>` | yes | Effective notification settings | Non-empty recipient key. |
| `--channel <name>` | yes | Effective notification settings | Non-empty NotiCLI channel name. |
| `--title <text>` | yes | Effective notification settings | Non-empty rendered title. |
| `--message <text>` | yes | Backup notification event plus settings | Non-empty rendered message. |

### Expected Results

| Exit Code | Meaning | vaultGFS Behavior |
|-----------|---------|-------------------|
| 0 | Notification accepted | Log notification success at diagnostic level appropriate for existing logs. |
| Non-zero | NotiCLI rejected or failed the request | Log notification failure with job, notification type, channel, recipient, exit code and diagnostics; keep original backup result. |
| Process not started | `noticli` missing or local execution error | Log notification failure with execution error; keep original backup result. |

### Logging Contract

Notification logs must identify:

- job name;
- notification type;
- effective channel;
- effective recipient;
- exit code when available;
- diagnostic output or execution error when available.

Notification logs must not expose configured secrets or credential-like values.
