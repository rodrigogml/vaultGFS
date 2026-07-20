from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3

from . import catalog


DEFAULT_FILESYSTEM_RETENTION = {"keep_full": 12, "keep_diff": 3, "keep_inc": 60}
DEFAULT_MONOLITH_RETENTION = {"keep_daily": 14, "keep_weekly": 8, "keep_monthly": 12}


@dataclass(frozen=True)
class PruneCandidate:
    run_id: int
    job_name: str
    job_type: str
    level: str
    destination: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class PrunePlan:
    keep_run_ids: frozenset[int]
    candidates: tuple[PruneCandidate, ...]


def retention_for_job(cfg: dict, job: dict) -> dict:
    typ = job["type"]
    section = "filesystem_gfs" if typ == "filesystem-gfs" else typ.replace("-", "_")
    defaults = cfg.get("defaults", {}).get("retention", {}).get(section, {})
    if not defaults and typ == "pfsense-config":
        defaults = cfg.get("defaults", {}).get("retention", {}).get("mysql_dump", {})
    built_in = DEFAULT_FILESYSTEM_RETENTION if typ == "filesystem-gfs" else DEFAULT_MONOLITH_RETENTION
    effective = {**built_in, **defaults, **job.get("retention", {})}
    return {k: int(v) for k, v in effective.items()}


def successful_runs(db: sqlite3.Connection, job: dict) -> list[sqlite3.Row]:
    return list(
        db.execute(
            """
            select *
            from backup_runs
            where job_name=? and job_type=? and status='success' and pruned_at is null
            order by id
            """,
            (job["name"], job["type"]),
        )
    )


def build_prune_plan(db: sqlite3.Connection, job: dict, retention: dict) -> PrunePlan:
    runs = successful_runs(db, job)
    if job["type"] == "filesystem-gfs":
        keep = filesystem_keep_ids(runs, retention)
    elif job["type"] in {"mysql-dump", "pfsense-config"}:
        keep = mysql_keep_ids(runs, retention)
    else:
        keep = set()
    candidates = tuple(candidate_for_run(db, job, run) for run in runs if run["id"] not in keep)
    return PrunePlan(frozenset(keep), candidates)


def filesystem_keep_ids(runs: list[sqlite3.Row], retention: dict) -> set[int]:
    keep: set[int] = set()
    by_id = {int(r["id"]): r for r in runs}
    inferred_parent = infer_filesystem_parents(runs)
    level_limits = {
        "full": retention.get("keep_full", 0),
        "diff": retention.get("keep_diff", 0),
        "inc": retention.get("keep_inc", 0),
    }

    for level in ("inc", "diff", "full"):
        selected = [r for r in reversed(runs) if r["level"] == level][: max(0, int(level_limits[level]))]
        for run in selected:
            mark_with_ancestors(keep, by_id, inferred_parent, int(run["id"]))
    return keep


def infer_filesystem_parents(runs: list[sqlite3.Row]) -> dict[int, int | None]:
    parents: dict[int, int | None] = {}
    latest_success: int | None = None
    latest_full: int | None = None
    for run in runs:
        run_id = int(run["id"])
        configured_parent = run["parent_run_id"]
        if configured_parent is not None:
            parent = int(configured_parent)
        elif run["level"] == "full":
            parent = None
        elif run["level"] == "diff":
            parent = latest_full
        else:
            parent = latest_success
        parents[run_id] = parent
        if run["level"] == "full":
            latest_full = run_id
        latest_success = run_id
    return parents


def mark_with_ancestors(keep: set[int], by_id: dict[int, sqlite3.Row], parents: dict[int, int | None], run_id: int):
    current: int | None = run_id
    while current is not None and current in by_id and current not in keep:
        keep.add(current)
        current = parents.get(current)


def mysql_keep_ids(runs: list[sqlite3.Row], retention: dict) -> set[int]:
    keep: set[int] = set()
    keep.update(latest_by_bucket(runs, lambda dt: dt.strftime("%Y-%m-%d"), retention.get("keep_daily", 0)))
    keep.update(latest_by_bucket(runs, sunday_week_bucket, retention.get("keep_weekly", 0)))
    keep.update(latest_by_bucket(runs, lambda dt: dt.strftime("%Y-%m"), retention.get("keep_monthly", 0)))
    return keep


def latest_by_bucket(runs: list[sqlite3.Row], bucket_fn, limit: int) -> set[int]:
    if limit <= 0:
        return set()
    buckets: dict[str, sqlite3.Row] = {}
    for run in runs:
        key = bucket_fn(run_datetime(run))
        old = buckets.get(key)
        if old is None or int(run["started_at"]) >= int(old["started_at"]):
            buckets[key] = run
    selected = sorted(buckets.values(), key=lambda r: int(r["started_at"]), reverse=True)
    return {int(r["id"]) for r in selected[:limit]}


def run_datetime(run: sqlite3.Row) -> datetime:
    return datetime.fromtimestamp(int(run["started_at"]))


def sunday_week_bucket(dt: datetime) -> str:
    start = dt.date().toordinal() - ((dt.weekday() + 1) % 7)
    return str(start)


def candidate_for_run(db: sqlite3.Connection, job: dict, run: sqlite3.Row) -> PruneCandidate:
    artifacts = [str(r["path"]) for r in catalog.artifacts_for_run(db, run["id"])]
    if not artifacts and job["type"] == "filesystem-gfs" and run["destination"]:
        artifacts = [str(run["destination"])]
    return PruneCandidate(
        run_id=int(run["id"]),
        job_name=job["name"],
        job_type=job["type"],
        level=str(run["level"] or "dump"),
        destination=str(run["destination"] or ""),
        paths=tuple(artifacts),
    )


def apply_prune(db: sqlite3.Connection, job: dict, candidate: PruneCandidate):
    if not candidate.paths:
        raise RuntimeError(f"run {candidate.run_id} has no cataloged artifacts to prune")
    dest_root = Path(job["destination"]).resolve(strict=False)
    for raw in candidate.paths:
        path = Path(raw).resolve(strict=False)
        ensure_inside(path, dest_root)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    catalog.mark_pruned(db, candidate.run_id, "removed by retention policy")


def ensure_inside(path: Path, dest_root: Path):
    try:
        path.relative_to(dest_root)
    except ValueError as exc:
        raise RuntimeError(f"refusing to prune path outside job destination: {path}") from exc
