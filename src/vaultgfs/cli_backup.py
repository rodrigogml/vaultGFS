from __future__ import annotations
import argparse, fcntl, os, sys, time
from datetime import datetime
from pathlib import Path
from .config import load_config, validate_config, DEFAULT_CONFIG
from .fs_backup import run_filesystem_job
from .mysql_dump import run_mysql_job

class BackupSlot:
    def __init__(self, cfg):
        defaults=cfg.get('defaults', {})
        self.state_dir=Path(defaults.get('state_dir', '/var/lib/vaultgfs'))
        self.max_slots=max(1, int(defaults.get('max_concurrent_backups', 1)))
        self.wait_seconds=max(1, int(defaults.get('lock_wait_seconds', 10)))
        self.fd=None
        self.path=None
    
    def acquire(self):
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
    try:
        if not job.get("enabled", True):
            print(f"SKIPPED {ns.job}: disabled")
            return 0
        if job["type"] == "filesystem-gfs":
            if not ns.level:
                print("--level is required for filesystem-gfs", file=sys.stderr)
                return 2
            return run_filesystem_job(cfg, job, ns.level)
        if job["type"] == "mysql-dump":
            return run_mysql_job(cfg, job)
        print(f"Unsupported job type: {job['type']}", file=sys.stderr)
        return 2
    finally:
        ended=datetime.now().isoformat(timespec="seconds")
        duration=time.time()-start
        print(f"RUN_END job={ns.job} level={ns.level or 'dump'} slot={slot} ended={ended} duration_seconds={duration:.3f}", flush=True)
        slotter.release()

if __name__ == "__main__":
    raise SystemExit(main())
