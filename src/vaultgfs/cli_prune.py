from __future__ import annotations

import argparse
import sys

from . import catalog
from .config import DEFAULT_CONFIG, load_config, validate_config
from .retention import apply_prune, build_prune_plan, retention_for_job


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prune vaultGFS backups according to retention policy")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--job")
    ap.add_argument("--apply", action="store_true", help="Remove selected artifacts. Omit for dry-run.")
    ns = ap.parse_args(argv)

    cfg = load_config(ns.config)
    errors = validate_config(cfg)
    if errors:
        print("Configuration errors:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 2

    jobs = [j for j in cfg["jobs"] if j.get("enabled", True)]
    if ns.job:
        jobs = [j for j in jobs if j.get("name") == ns.job]
        if not jobs:
            print(f"Job not found: {ns.job}", file=sys.stderr)
            return 2

    db = catalog.connect(cfg.get("defaults", {}).get("catalog", "/var/lib/vaultgfs/catalog.db"))
    mode = "APPLY" if ns.apply else "DRY_RUN"
    total = 0
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
                    print(f"PRUNE_SKIPPED job={candidate.job_name} run_id={candidate.run_id} reason=no_cataloged_artifacts")
                    continue
                apply_prune(db, job, candidate)
                print(f"PRUNED job={candidate.job_name} run_id={candidate.run_id}")
    print(f"PRUNE_DONE mode={mode} candidates={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
