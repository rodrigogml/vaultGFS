from __future__ import annotations
import argparse, os, sys, time
from datetime import datetime
from pathlib import Path
from .config import load_config, validate_config, DEFAULT_CONFIG
from .fs_backup import run_filesystem_job
from .mysql_dump import run_mysql_job
from .notification import NotificationEvent, log_delivery, resolve_settings, send_notification

try:
    import fcntl
except ImportError:
    fcntl = None

class BackupSlot:
    def __init__(self, cfg):
        defaults=cfg.get('defaults', {})
        self.state_dir=Path(defaults.get('state_dir', '/var/lib/vaultgfs'))
        self.max_slots=max(1, int(defaults.get('max_concurrent_backups', 1)))
        self.wait_seconds=max(1, int(defaults.get('lock_wait_seconds', 10)))
        self.fd=None
        self.path=None
    
    def acquire(self):
        if fcntl is None:
            raise RuntimeError("backup slot locking requires fcntl")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        while True:
            for slot in range(self.max_slots):
                path=self.state_dir / f'vaultgfs-backup-{slot}.lock'
                fd=os.open(path, os.O_RDWR | os.O_CREAT, 0o660)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    os.ftruncate(fd, 0)
                    os.write(fd, f'pid={os.getpid()} slot={slot} started={datetime.now().isoformat(timespec="seconds")}\n'.encode())
                    self.fd=fd; self.path=path
                    return slot
                except BlockingIOError:
                    os.close(fd)
            print(f'WAIT concurrency: all {self.max_slots} backup slot(s) busy; sleeping {self.wait_seconds}s', flush=True)
            time.sleep(self.wait_seconds)
    
    def release(self):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
            self.fd=None

def main(argv=None):
    ap=argparse.ArgumentParser(description="Run vaultGFS backup jobs")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--job", required=True)
    ap.add_argument("--level", choices=["full","diff","inc"])
    ns=ap.parse_args(argv)
    cfg=load_config(ns.config)
    errors=validate_config(cfg)
    if errors:
        print("Configuration errors:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 2
    job=next((j for j in cfg["jobs"] if j.get("name") == ns.job), None)
    if not job:
        print(f"Job not found: {ns.job}", file=sys.stderr)
        return 2
    queued_at=datetime.now().isoformat(timespec="seconds")
    queue_start_ts=time.time()
    slotter=BackupSlot(cfg)
    slot=slotter.acquire()
    start=time.time()
    started=datetime.now().isoformat(timespec="seconds")
    queue_seconds=start-queue_start_ts
    print(f"QUEUE_INFO job={ns.job} level={ns.level or 'dump'} queued_at={queued_at} started={started} queue_seconds={queue_seconds:.3f} slot={slot}", flush=True)
    print(f"RUN_START job={ns.job} level={ns.level or 'dump'} slot={slot} started={started}", flush=True)
    rc=1
    status='failed'
    summary='backup did not complete'
    should_notify=True
    try:
        if not job.get("enabled", True):
            print(f"SKIPPED {ns.job}: disabled")
            should_notify=False
            rc=0
            status='skipped'
            summary='job disabled'
        if should_notify and job["type"] == "filesystem-gfs":
            if not ns.level:
                print("--level is required for filesystem-gfs", file=sys.stderr)
                rc=2
                summary='missing filesystem backup level'
            else:
                rc=run_filesystem_job(cfg, job, ns.level)
                status='success' if rc == 0 else 'failed'
                summary=f'filesystem backup completed with exit_code={rc}'
        elif job["type"] == "mysql-dump" and should_notify:
            rc=run_mysql_job(cfg, job)
            status='success' if rc == 0 else 'failed'
            summary=f'mysql backup completed with exit_code={rc}'
        elif should_notify:
            print(f"Unsupported job type: {job['type']}", file=sys.stderr)
            rc=2
            summary=f"unsupported job type: {job['type']}"
        return rc
    except Exception as exc:
        status='failed'
        summary=str(exc)
        raise
    finally:
        ended=datetime.now().isoformat(timespec="seconds")
        duration=time.time()-start
        event=None
        if should_notify:
            event=NotificationEvent(
                job_name=ns.job,
                job_type=job.get('type', ''),
                level=ns.level or 'dump',
                status=status,
                started_at=started,
                ended_at=ended,
                duration_seconds=duration,
                summary=summary,
            )
        print(f"RUN_END job={ns.job} level={ns.level or 'dump'} slot={slot} ended={ended} duration_seconds={duration:.3f}", flush=True)
        slotter.release()
        if event is not None:
            settings=resolve_settings(cfg, job, event)
            result=send_notification(settings)
            log_delivery(ns.job, settings, result)

if __name__ == "__main__":
    raise SystemExit(main())
