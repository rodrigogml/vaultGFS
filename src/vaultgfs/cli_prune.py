from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from . import catalog
from .config import DEFAULT_CONFIG, load_config, validate_config
from .notification import NotificationEvent, log_delivery, resolve_settings, send_notification
from .retention import apply_prune, build_prune_plan, retention_for_job


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prune vaultGFS backups according to retention policy")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--job")
    ap.add_argument("--apply", action="store_true", help="Remove selected artifacts. Omit for dry-run.")
    ns = ap.parse_args(argv)
    started = datetime.now().isoformat(timespec="seconds")
    start = time.time()
    status = "failed"
    summary = "prune did not complete"
    cfg = None

    try:
        cfg = load_config(ns.config)
        errors = validate_config(cfg)
        if errors:
            print("Configuration errors:", file=sys.stderr)
            print("\n".join(errors), file=sys.stderr)
            summary = "configuration validation failed"
            return 2

        jobs = [j for j in cfg["jobs"] if j.get("enabled", True)]
        if ns.job:
            jobs = [j for j in jobs if j.get("name") == ns.job]
            if not jobs:
                print(f"Job not found: {ns.job}", file=sys.stderr)
                summary = f"job not found: {ns.job}"
                return 2

        db = catalog.connect(cfg.get("defaults", {}).get("catalog", "/var/lib/vaultgfs/catalog.db"))
        mode = "APPLY" if ns.apply else "DRY_RUN"
        total = 0
        pruned = 0
        skipped = 0
        for job in jobs:
            retention = retention_for_job(cfg, job)
            plan = build_prune_plan(db, job, retention)
            print(f"PRUNE_PLAN mode={mode} job={job['name']} keep={len(plan.keep_run_ids)} prune={len(plan.candidates)}")
            for candidate in plan.candidates:
                paths = ",".join(candidate.paths) if candidate.paths else "-"
                print(f"PRUNE_CANDIDATE job={candidate.job_name} run_id={candidate.run_id} level={candidate.level} paths={paths}")
                total += 1
                if ns.apply:
                    if not candidate.paths:
                        skipped += 1
                        print(f"PRUNE_SKIPPED job={candidate.job_name} run_id={candidate.run_id} reason=no_cataloged_artifacts")
                        continue
                    apply_prune(db, job, candidate)
                    pruned += 1
                    print(f"PRUNED job={candidate.job_name} run_id={candidate.run_id}")
        summary = f"mode={mode} candidates={total} pruned={pruned} skipped={skipped}"
        status = "success"
        print(f"PRUNE_DONE {summary}")
        return 0
    except Exception as exc:
        summary = str(exc)
        raise
    finally:
        if cfg is not None:
            ended = datetime.now().isoformat(timespec="seconds")
            event = NotificationEvent(
                job_name="vaultgfs-prune",
                job_type="retention-prune",
                level="apply" if ns.apply else "dry-run",
                status=status,
                started_at=started,
                ended_at=ended,
                duration_seconds=time.time() - start,
                summary=summary,
            )
            settings = resolve_settings(cfg, {}, event)
            result = send_notification(settings)
            log_delivery(event.job_name, settings, result)


if __name__ == "__main__":
    raise SystemExit(main())
