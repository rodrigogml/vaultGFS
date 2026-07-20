from __future__ import annotations

from datetime import datetime

from vaultgfs import catalog, cli_prune
from vaultgfs.retention import build_prune_plan, retention_for_job


def ts(year, month, day, hour=0):
    return int(datetime(year, month, day, hour).timestamp())


def add_run(db, run_id, job, level, started_at, destination, parent_run_id=None):
    db.execute(
        """
        insert into backup_runs(id,job_name,job_type,level,status,started_at,finished_at,destination,parent_run_id)
        values(?,?,?,?,?,?,?,?,?)
        """,
        (run_id, job["name"], job["type"], level, "success", started_at, started_at + 1, destination, parent_run_id),
    )
    db.commit()


def test_filesystem_retention_keeps_incremental_ancestors():
    db = catalog.connect(":memory:")
    job = {"name": "files", "type": "filesystem-gfs", "destination": "/backup/files"}
    add_run(db, 1, job, "full", ts(2026, 1, 1), "/backup/files/full/1")
    add_run(db, 2, job, "diff", ts(2026, 1, 7), "/backup/files/diff/2", 1)
    add_run(db, 3, job, "inc", ts(2026, 1, 8), "/backup/files/inc/3", 2)
    add_run(db, 4, job, "inc", ts(2026, 1, 9), "/backup/files/inc/4", 3)

    plan = build_prune_plan(db, job, {"keep_full": 0, "keep_diff": 0, "keep_inc": 1})

    assert plan.keep_run_ids == {1, 2, 3, 4}
    assert plan.candidates == ()


def test_filesystem_retention_prunes_unneeded_old_full():
    db = catalog.connect(":memory:")
    job = {"name": "files", "type": "filesystem-gfs", "destination": "/backup/files"}
    add_run(db, 1, job, "full", ts(2025, 12, 1), "/backup/files/full/1")
    add_run(db, 2, job, "full", ts(2026, 1, 1), "/backup/files/full/2")

    plan = build_prune_plan(db, job, {"keep_full": 1, "keep_diff": 0, "keep_inc": 0})

    assert plan.keep_run_ids == {2}
    assert [c.run_id for c in plan.candidates] == [1]


def test_mysql_retention_uses_latest_daily_weekly_monthly_buckets():
    db = catalog.connect(":memory:")
    job = {"name": "mysql", "type": "mysql-dump", "destination": "/backup/mysql"}
    add_run(db, 1, job, "dump", ts(2026, 6, 30), "/backup/mysql")
    add_run(db, 2, job, "dump", ts(2026, 7, 1), "/backup/mysql")
    add_run(db, 3, job, "dump", ts(2026, 7, 2), "/backup/mysql")
    add_run(db, 4, job, "dump", ts(2026, 7, 8), "/backup/mysql")

    plan = build_prune_plan(db, job, {"keep_daily": 1, "keep_weekly": 1, "keep_monthly": 2})

    assert plan.keep_run_ids == {1, 4}
    assert [c.run_id for c in plan.candidates] == [2, 3]


def test_prune_cli_dry_run_and_apply_filesystem_artifact(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    backup_root = tmp_path / "backup"
    old_run = backup_root / "full" / "old"
    new_run = backup_root / "full" / "new"
    old_run.mkdir(parents=True)
    new_run.mkdir(parents=True)
    (old_run / "manifest.json").write_text("{}", encoding="utf-8")
    (new_run / "manifest.json").write_text("{}", encoding="utf-8")
    db_path = tmp_path / "catalog.db"
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
[defaults]
catalog = "{db_path}"

[[jobs]]
name = "files"
enabled = true
type = "filesystem-gfs"
source = "{source}"
destination = "{backup_root}"
schedule_full = "0 1 1 * *"
schedule_diff = "0 1 * * 0"
schedule_inc = "0 1 * * *"

[jobs.retention]
keep_full = 1
keep_diff = 0
keep_inc = 0
""".strip(),
        encoding="utf-8",
    )
    db = catalog.connect(db_path)
    job = {"name": "files", "type": "filesystem-gfs"}
    add_run(db, 1, job, "full", ts(2026, 1, 1), str(old_run))
    add_run(db, 2, job, "full", ts(2026, 2, 1), str(new_run))
    catalog.insert_artifacts(db, 1, [old_run], "filesystem-run")
    catalog.insert_artifacts(db, 2, [new_run], "filesystem-run")

    assert cli_prune.main(["--config", str(config), "--job", "files"]) == 0
    assert old_run.exists()

    assert cli_prune.main(["--config", str(config), "--job", "files", "--apply"]) == 0
    assert not old_run.exists()
    row = db.execute("select pruned_at from backup_runs where id=1").fetchone()
    assert row["pruned_at"] is not None


def test_retention_for_job_uses_defaults_and_job_overrides():
    cfg = {
        "defaults": {"retention": {"filesystem_gfs": {"keep_full": 5, "keep_diff": 4, "keep_inc": 3}}},
    }
    job = {"type": "filesystem-gfs", "retention": {"keep_inc": 9}}

    assert retention_for_job(cfg, job) == {"keep_full": 5, "keep_diff": 4, "keep_inc": 9}
