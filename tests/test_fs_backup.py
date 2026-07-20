from __future__ import annotations

from datetime import datetime

from vaultgfs import catalog
from vaultgfs.fs_backup import effective_filesystem_level


def ts(year, month, day, hour=0, minute=0):
    return int(datetime(year, month, day, hour, minute).timestamp())


def add_success(db, run_id, level, started_at):
    db.execute(
        """
        insert into backup_runs(id,job_name,job_type,level,status,started_at)
        values(?,?,?,?,?,?)
        """,
        (run_id, "files", "filesystem-gfs", level, "success", started_at),
    )
    db.commit()


def job():
    return {
        "name": "files",
        "type": "filesystem-gfs",
        "schedule_full": "0 3 1 * *",
        "schedule_diff": "0 2 * * 0",
        "schedule_inc": "0 1 * * *",
    }


def test_incremental_promotes_to_full_when_no_full_exists():
    db = catalog.connect(":memory:")

    assert effective_filesystem_level(db, job(), "inc", datetime(2026, 7, 20, 4, 0)) == "full"


def test_incremental_promotes_to_full_when_full_schedule_is_due():
    db = catalog.connect(":memory:")
    add_success(db, 1, "full", ts(2026, 6, 1, 3))
    add_success(db, 2, "diff", ts(2026, 6, 28, 2))

    assert effective_filesystem_level(db, job(), "inc", datetime(2026, 7, 2, 4, 0)) == "full"


def test_incremental_promotes_to_diff_when_weekly_diff_is_due():
    db = catalog.connect(":memory:")
    add_success(db, 1, "full", ts(2026, 7, 1, 3))
    add_success(db, 2, "diff", ts(2026, 7, 12, 2))

    assert effective_filesystem_level(db, job(), "inc", datetime(2026, 7, 20, 4, 0)) == "diff"


def test_incremental_remains_incremental_when_parent_schedules_are_current():
    db = catalog.connect(":memory:")
    add_success(db, 1, "full", ts(2026, 7, 1, 3))
    add_success(db, 2, "diff", ts(2026, 7, 19, 2))

    assert effective_filesystem_level(db, job(), "inc", datetime(2026, 7, 20, 4, 0)) == "inc"


def test_diff_promotes_to_full_when_full_schedule_is_due():
    db = catalog.connect(":memory:")
    add_success(db, 1, "full", ts(2026, 6, 1, 3))

    assert effective_filesystem_level(db, job(), "diff", datetime(2026, 7, 2, 4, 0)) == "full"
