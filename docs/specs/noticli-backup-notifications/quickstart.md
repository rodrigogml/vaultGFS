# Quickstart: NotiCLI Backup Notifications

Cenários de teste que validam a implementação end-to-end.

## Scenario 1: Global Success Notification

1. Configure global NotiCLI notification settings in the vaultGFS TOML configuration with notifications enabled.
2. Provide a fake `noticli` executable earlier in PATH that records received arguments and returns exit code `0`.
3. Run a successful backup job.
4. **Expected**: vaultGFS finishes the backup successfully and the fake NotiCLI receives exactly one `noticli send` request with sender, recipient, channel, title and message.

## Scenario 2: Job Override Notification

1. Configure global NotiCLI defaults.
2. Configure one job with a different recipient and no job-specific channel.
3. Run that job.
4. **Expected**: the notification uses the job recipient and the global channel.

## Scenario 3: Failure-Specific Notification

1. Configure default notification settings and failure-specific settings with a distinct title or sender.
2. Run a job that fails.
3. **Expected**: vaultGFS sends one failure notification using failure-specific fields where present and inherited defaults for the remaining fields.

## Scenario 4: NotiCLI Delivery Failure Does Not Fail Backup

1. Configure notifications for a job that otherwise succeeds.
2. Provide a fake `noticli` executable that returns a non-zero exit code and diagnostic text.
3. Run the backup job.
4. **Expected**: vaultGFS keeps the backup result successful and logs the notification failure with job name, notification type, recipient, channel, exit code and diagnostic text.

## Scenario 5: Notifications Disabled

1. Disable NotiCLI notifications globally.
2. Run a backup job.
3. **Expected**: vaultGFS does not invoke `noticli` and the backup behavior is unchanged.
