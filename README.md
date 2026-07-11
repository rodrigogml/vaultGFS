# vaultGFS

`vaultGFS` is a Python backup utility for filesystem jobs and logical MySQL dumps. It organizes filesystem backups with a GFS-style model: monthly full backups, weekly differentials, and daily incrementals.

The project is packaged as a standard Python distribution with console entrypoints. Runtime configuration is intentionally kept outside the repository; `config.toml.model` is the versioned reference configuration.

## Features

- Filesystem backup jobs with `full`, `diff`, and `inc` levels.
- MySQL logical dumps per schema, compressed with `zstd`.
- SQLite catalog for runs and filesystem snapshots.
- Per-run `manifest.json` for filesystem backups.
- Global process-safe backup slot lock for queueing concurrent starts.
- Separate archives for already-compressed files and compressible files.
- Optional MySQL resource monitoring with passive logging or active throttling.
- Optional backup result notifications through NotiCLI.
- Assisted environment reload that validates configuration and generates systemd units/timers.
- TOML-based configuration.

## Repository Layout

```text
vaultGFS/
├── config.toml.model        # versioned reference configuration
├── docs/requirements.md     # requirements and design notes
├── pyproject.toml           # package metadata, build backend, entrypoints
├── README.md
└── src/vaultgfs/
    ├── __init__.py
    ├── catalog.py           # SQLite catalog
    ├── cli_backup.py        # vaultgfs-backup entrypoint
    ├── cli_reload.py        # vaultgfs-reload entrypoint
    ├── cli_restore.py       # vaultgfs-restore placeholder
    ├── config.py            # TOML loading and validation
    ├── fs_backup.py         # filesystem/GFS backup implementation
    └── mysql_dump.py        # MySQL dump implementation
```

Generated files such as `dist/`, `build/`, `*.egg-info`, logs, catalogs, and real configuration files are not part of the source tree.

## Requirements

- Linux.
- Python 3.11+.
- `tar`.
- `zstd`.
- `mysqldump` and `mysql` when using MySQL jobs.
- `systemd` when using `vaultgfs-reload` to generate timers.
- `noticli` on the system `PATH` when NotiCLI notifications are enabled.

## Build

Install the build frontend in your development environment:

```bash
python3 -m pip install build
```

Build the source distribution and wheel:

```bash
python3 -m build
```

Expected artifacts:

```text
dist/vaultgfs-<version>.tar.gz
dist/vaultgfs-<version>-py3-none-any.whl
```

## Installation

Install from a release wheel:

```bash
python3 -m pip install vaultgfs-<version>-py3-none-any.whl
```

For isolated deployments, install into a dedicated virtual environment:

```bash
python3 -m venv /path/to/venv
/path/to/venv/bin/python -m pip install vaultgfs-<version>-py3-none-any.whl
```

The package provides these console scripts:

```text
vaultgfs-backup
vaultgfs-reload
vaultgfs-restore
```

Development installs are supported when working on the source tree:

```bash
python3 -m pip install -e .
```

## Configuration

The default configuration path is:

```text
/opt/vaultGFS/config.toml
```

Use `config.toml.model` as the starting point for a real configuration:

```bash
cp config.toml.model config.toml
```

Do not commit real configuration files. They may contain credentials and host-specific paths.

Minimum configuration shape:

```toml
[defaults]
state_dir = "/var/lib/vaultgfs"
catalog = "/var/lib/vaultgfs/catalog.db"
destination_root = "/mnt/backup"
run_user = "vaultgfs"
run_group = "vaultgfs"
compression_level = 22
compression_threads = 2
max_concurrent_backups = 1
lock_wait_seconds = 10

storage_extensions = [".jpg", ".png", ".mp4", ".zip", ".7z", ".pdf"]

[mysql]
host = "localhost"
port = 3306
user = "vaultGFS"
password = "CHANGE_ME"
socket = "/var/run/mysqld/mysqld.sock"
ssl_mode = "DISABLED"
```

`max_concurrent_backups` controls the number of backup jobs that can run at the same time. When all slots are busy, new processes wait and log `WAIT concurrency` every `lock_wait_seconds`. This value is not a timeout.

## Filesystem Jobs

Example:

```toml
[[jobs]]
name = "example-filesystem"
enabled = true
type = "filesystem-gfs"
source = "/data/example"
destination = "/mnt/backup/example-filesystem"
skip_if_unchanged = true
compression_level = 22
compression_threads = 2
schedule_full = "0 3 1 * *"
schedule_diff = "0 2 * * 0"
schedule_inc = "0 1 * * *"
```

Run manually:

```bash
vaultgfs-backup --config /path/to/config.toml --job example-filesystem --level full
vaultgfs-backup --config /path/to/config.toml --job example-filesystem --level diff
vaultgfs-backup --config /path/to/config.toml --job example-filesystem --level inc
```

Filesystem output:

```text
<destination>/<level>/<job>-<level>-YYYYMMDD-HHMMSS/
├── <job>-<level>-YYYYMMDD-HHMMSS.storage.tar
├── <job>-<level>-YYYYMMDD-HHMMSS.compressible.tar.zst
└── manifest.json
```

Only archives with selected files are created. A run may contain only `storage.tar`, only `compressible.tar.zst`, or both.

## MySQL Jobs

Example:

```toml
[[jobs]]
name = "example-mysql"
enabled = true
type = "mysql-dump"
schemas = ["example_schema"]
destination = "/mnt/backup/mysql/example_schema"
compression_level = 22
compression_threads = 1
resource_monitor = "passive"
nice = 15
ionice_class = 2
ionice_level = 7
schedule = "0 4 * * *"
```

Run manually:

```bash
vaultgfs-backup --config /path/to/config.toml --job example-mysql
```

MySQL output:

```text
<destination>/<schema>-YYYYMMDD-HHMMSS.sql.zst
```

System schemas are rejected as backup targets:

```text
mysql
information_schema
performance_schema
sys
```

Recommended minimum MySQL privileges:

```sql
GRANT SELECT, SHOW VIEW, EVENT, TRIGGER ON schema.* TO 'vaultGFS'@'localhost';
GRANT SHOW_ROUTINE ON *.* TO 'vaultGFS'@'localhost';
```

## Resource Monitoring

MySQL jobs support `resource_monitor`:

- `off`: no monitor logs.
- `passive`: logs metrics without interfering.
- `active`: may pause, resume, or abort dump/compression subprocesses when configured limits are exceeded.

Supported limit keys include:

```toml
monitor_interval_seconds = 10
pause_seconds = 15
max_pause_cycles = 20
abort_if_sustained_seconds = 300
max_cpu_percent = 80
max_memory_percent = 50
max_load_1m = 4
max_swap_percent = 80
```

The monitor observes the `mysqldump` and `zstd` subprocesses. It does not cap MySQL server-side I/O or memory usage.

## Environment Reload

`vaultgfs-reload` validates the configuration and proposes environment changes:

```bash
vaultgfs-reload --config /path/to/config.toml
```

With `--yes`, all proposed actions are applied:

```bash
vaultgfs-reload --config /path/to/config.toml --yes
```

Current actions include:

- Validate required job fields.
- Check the configured run user.
- Create missing state and destination directories.
- Warn about missing filesystem sources.
- Validate MySQL schema access.
- Write systemd `.service` and `.timer` units for enabled jobs.
- Remove obsolete `vaultgfs-*` systemd units.
- Reload systemd and enable/start generated timers.

The generated services call `vaultgfs-backup` and rely on the global lock for concurrency control.

## NotiCLI Notifications

vaultGFS can optionally call `noticli send` after a backup execution finishes. NotiCLI is an external executable and must be available on the system `PATH`; vaultGFS does not embed or install it.

See the [NotiCLI repository](https://github.com/rodrigogml/NotiCLI) for NotiCLI installation, destination, delivery account and route setup.

Global configuration uses the existing TOML configuration file:

```toml
[notifications.noticli]
enabled = true
config = "/opt/NotiCLI/config/noticli.json" # optional
sender = "vaultGFS"
category = "SUCCESS"
title = "vaultGFS backup {status}: {job_name}"
message = "job={job_name} level={level} status={status} summary={summary}"

[notifications.noticli.failure]
category = "FAIL"
priority = "HIGH"
title = "vaultGFS BACKUP FAILED: {job_name}"
```

Jobs may override the same fields. Omitted job fields inherit the effective global value:

```toml
[[jobs]]
name = "example-filesystem"
type = "filesystem-gfs"
# remaining job fields...

[jobs.notifications.noticli]
category = "FILESYSTEM"

[jobs.notifications.noticli.failure]
category = "FAIL"
priority = "HIGH"
title = "Filesystem backup failed: {job_name}"
```

Supported placeholders in `title` and `message` are `{job_name}`, `{job_type}`, `{level}`, `{status}`, `{started_at}`, `{ended_at}`, `{duration_seconds}` and `{summary}`.

Supported vaultGFS NotiCLI settings:

| Setting | Required when enabled | Description |
|---------|-----------------------|-------------|
| `enabled` | no | Enables or disables NotiCLI notifications globally or for one job. Defaults to disabled globally. |
| `config` | no | Optional path passed as `noticli send --config`. If omitted, NotiCLI uses its own default config lookup. |
| `sender` | yes | Value passed as `--sender`; keep it at 20 characters or less to match NotiCLI constraints. |
| `category` | yes | Value passed as `--category`; defaults should use `SUCCESS` for successful backups and `FAIL` for failed backups. |
| `priority` | no | Optional value passed as `--priority`; use `HIGH` for failed backups and omit it for successful backups. |
| `title` | yes | Notification title passed as `--title`; supports vaultGFS placeholders. |
| `message` | no | Notification body passed as `--message`; supports vaultGFS placeholders. If omitted, vaultGFS renders a default execution summary. |
| `failure` | no | Nested table with values that override default notification settings only for failed backups. |

Notification delivery failures are logged as `NOTIFICATION_FAILED` with job, notification type, category, priority, exit code and diagnostics when available. They do not interrupt the backup flow and do not change the final backup result.

## Logs And Catalog

Every backup run logs queue and runtime boundaries:

```text
QUEUE_INFO job=example-filesystem level=full queued_at=... started=... queue_seconds=... slot=0
RUN_START job=example-filesystem level=full slot=0 started=...
SUCCESS example-filesystem full: 123 files -> /backup/path
RUN_END job=example-filesystem level=full slot=0 ended=... duration_seconds=...
```

`QUEUE_INFO` measures time spent waiting for a backup slot. `RUN_END.duration_seconds` measures job execution after the slot is acquired.

The SQLite catalog path is configured by `defaults.catalog`. It stores backup runs, statuses, destination paths, manifests, and filesystem snapshots used to calculate differential and incremental selections. The catalog is runtime state and must not be committed.

## Restore

`vaultgfs-restore` is currently a placeholder:

```bash
vaultgfs-restore
```

Current output:

```text
vaultgfs-restore is planned for a future version.
```

## Artifact Validation

Validate an uncompressed archive:

```bash
tar -tf backup.storage.tar
```

Validate a compressed filesystem archive:

```bash
zstd -t backup.compressible.tar.zst
tar --use-compress-program='zstd -d' -tf backup.compressible.tar.zst
```

Validate a compressed MySQL dump:

```bash
zstd -t schema-YYYYMMDD-HHMMSS.sql.zst
```

## Security

- Do not commit real `config.toml` files.
- Do not commit credentials, dumps, logs, catalogs, or generated artifacts.
- Use a dedicated system user for backup execution.
- Restrict read access to configuration files containing credentials.
- Grant the MySQL backup user only the privileges required for logical dumps.
- Run backup processes with appropriate CPU and I/O priority for the host.

## Current Scope

Implemented:

- Filesystem `full`, `diff`, and `inc` backups.
- MySQL schema dumps.
- `zstd` compression.
- SQLite catalog and filesystem manifests.
- Global backup queue lock.
- MySQL resource monitoring.
- systemd unit/timer generation through `vaultgfs-reload`.

Planned:

- Interactive restore workflow.
- Retention/rotation policy.
- External/off-site copy workflow.
- Filesystem resource monitoring.
