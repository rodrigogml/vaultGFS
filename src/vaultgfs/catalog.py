from __future__ import annotations
import sqlite3, time
from pathlib import Path

def connect(path: str | Path):
	Path(path).parent.mkdir(parents=True, exist_ok=True)
	db=sqlite3.connect(str(path))
	db.row_factory=sqlite3.Row
	init(db)
	return db

def init(db):
	db.executescript("""
	create table if not exists backup_runs (
	 id integer primary key autoincrement,
	 job_name text not null,
	 job_type text not null,
	 level text,
	 status text not null,
	 started_at integer not null,
	 finished_at integer,
	 destination text,
	 manifest_path text,
	 message text
	);
	create table if not exists file_snapshots (
	 run_id integer not null,
	 job_name text not null,
	 relpath text not null,
	 size integer not null,
	 mtime_ns integer not null,
	 mode integer not null,
	 uid integer not null,
	 gid integer not null,
	 sha256 text,
	 class text,
	 primary key(run_id, relpath)
	);
	create index if not exists idx_runs_job_status on backup_runs(job_name,status,level,id);
	""")
	db.commit()

def start_run(db, job, level):
	cur=db.execute("insert into backup_runs(job_name,job_type,level,status,started_at) values(?,?,?,?,?)", (job['name'], job['type'], level, 'running', int(time.time())))
	db.commit()
	return cur.lastrowid

def finish_run(db, run_id, status, destination=None, manifest_path=None, message=None):
	db.execute("update backup_runs set status=?, finished_at=?, destination=?, manifest_path=?, message=? where id=?", (status, int(time.time()), destination, manifest_path, message, run_id))
	db.commit()

def last_success_run(db, job_name, level=None):
	if level:
		cur=db.execute("select * from backup_runs where job_name=? and status='success' and level=? order by id desc limit 1", (job_name, level))
	else:
		cur=db.execute("select * from backup_runs where job_name=? and status='success' order by id desc limit 1", (job_name,))
	return cur.fetchone()

def snapshot_map(db, run_id):
	return {r['relpath']: r for r in db.execute("select relpath,size,mtime_ns from file_snapshots where run_id=?", (run_id,))}

def insert_snapshots(db, rows):
	db.executemany("insert or replace into file_snapshots(run_id,job_name,relpath,size,mtime_ns,mode,uid,gid,sha256,class) values(?,?,?,?,?,?,?,?,?,?)", rows)
	db.commit()
