from __future__ import annotations
import argparse, os, pwd, re, shlex, subprocess, sys
from pathlib import Path
from .config import load_config, validate_config, DEFAULT_CONFIG

SYSTEMD_DIR = Path("/etc/systemd/system")

def sanitize(name: str) -> str:
	return re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")

def cron_to_oncalendar(expr: str) -> str:
	parts = expr.split()
	if len(parts) != 5:
		raise ValueError(f"invalid cron expression: {expr}")
	minute, hour, dom, month, dow = parts
	dow_map = {"0":"Sun", "7":"Sun", "1":"Mon", "2":"Tue", "3":"Wed", "4":"Thu", "5":"Fri", "6":"Sat"}
	sdow = "*" if dow == "*" else ",".join(dow_map.get(x, x) for x in dow.split(","))
	return f"{sdow} *-{month}-{dom} {hour}:{minute}:00"

def unit_pair(job: dict, kind: str, cron: str, level: str | None):
	safe = sanitize(f"vaultgfs-{job['name']}-{kind}")
	service = SYSTEMD_DIR / f"{safe}.service"
	timer = SYSTEMD_DIR / f"{safe}.timer"
	cmd = f"/usr/local/bin/vaultgfs-backup --job {shlex.quote(job['name'])}"
	if level:
		cmd += f" --level {level}"
	svc = f"""[Unit]
Description=vaultGFS backup {job['name']} {kind}

[Service]
Type=oneshot
User=vaultgfs
Group=vaultgfs
ExecStart={cmd}
"""
	tmr = f"""[Unit]
Description=vaultGFS timer {job['name']} {kind}

[Timer]
OnCalendar={cron_to_oncalendar(cron)}
Persistent=true
Unit={safe}.service

[Install]
WantedBy=timers.target
"""
	return service, svc, timer, tmr

def desired_units(cfg: dict):
	units = {}
	for job in cfg.get("jobs", []):
		if not job.get("enabled", True):
			continue
		if job["type"] == "filesystem-gfs":
			items = [("full","schedule_full","full"), ("diff","schedule_diff","diff"), ("inc","schedule_inc","inc")]
		elif job["type"] == "mysql-dump":
			items = [("dump","schedule",None)]
		else:
			items = []
		for kind, field, level in items:
			s, sc, t, tc = unit_pair(job, kind, job[field], level)
			units[s] = sc
			units[t] = tc
	return units


def mysql_check_command(cfg: dict, schema: str):
	mysql = cfg.get("mysql", {})
	cmd = ["mysql"]
	if mysql.get("socket"):
		cmd += ["--socket", mysql["socket"]]
	else:
		cmd += ["--host", mysql.get("host", "localhost"), "--port", str(mysql.get("port", 3306))]
	if mysql.get("user"):
		cmd += ["--user", mysql["user"]]
	if mysql.get("password"):
		cmd += [f"--password={mysql['password']}"]
	cmd += ["--batch", "--skip-column-names", "-e", f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='{schema}'"]
	return cmd

def add(actions, desc, fn):
	actions.append((desc, fn))

def main(argv=None):
	ap = argparse.ArgumentParser(description="Validate vaultGFS config and sync systemd timers")
	ap.add_argument("--config", default=DEFAULT_CONFIG)
	ap.add_argument("--yes", action="store_true")
	ns = ap.parse_args(argv)
	cfg = load_config(ns.config)
	errors = validate_config(cfg)
	if errors:
		print("Configuration errors:")
		print("\n".join(errors))
		return 2
	actions=[]
	defaults = cfg.get("defaults", {})
	run_user = defaults.get("run_user", "vaultgfs")
	try:
		pwd.getpwnam(run_user)
	except KeyError:
		add(actions, f"Create Linux user {run_user}", lambda: subprocess.run(["useradd","--system","--home","/var/lib/vaultgfs","--shell","/usr/sbin/nologin",run_user], check=True))
	for d in [defaults.get("state_dir","/var/lib/vaultgfs"), defaults.get("destination_root","/mnt/usb1/backups")]:
		p=Path(d)
		if not p.exists():
			add(actions, f"Create directory {p}", lambda p=p: p.mkdir(parents=True, exist_ok=True))
	for job in cfg.get("jobs", []):
		if not job.get("enabled", True):
			continue
		if job["type"] == "filesystem-gfs" and not Path(job["source"]).exists():
			print(f"WARNING: missing source for {job['name']}: {job['source']}")
		dst=Path(job["destination"])
		if not dst.exists():
			add(actions, f"Create destination for {job['name']}: {dst}", lambda dst=dst: dst.mkdir(parents=True, exist_ok=True))
	for job in cfg.get("jobs", []):
		if job.get("enabled", True) and job.get("type") == "mysql-dump":
			for schema in job.get("schemas", []):
				try:
					subprocess.run(mysql_check_command(cfg, schema), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=True)
				except Exception:
					print(f"WARNING: MySQL access validation failed for job {job['name']} schema {schema}")
	units=desired_units(cfg)
	for path, content in units.items():
		if not path.exists() or path.read_text() != content:
			add(actions, f"Write systemd unit {path}", lambda path=path, content=content: path.write_text(content))
	for p in list(SYSTEMD_DIR.glob("vaultgfs-*.service")) + list(SYSTEMD_DIR.glob("vaultgfs-*.timer")):
		if p not in units:
			add(actions, f"Remove obsolete systemd unit {p}", lambda p=p: p.unlink(missing_ok=True))
	if units:
		add(actions, "Reload systemd daemon", lambda: subprocess.run(["systemctl","daemon-reload"], check=True))
		for p in units:
			if p.suffix == ".timer":
				add(actions, f"Enable/start timer {p.name}", lambda p=p: subprocess.run(["systemctl","enable","--now",p.name], check=True))
	if not actions:
		print("vaultGFS reload: no changes required.")
		return 0
	print("Proposed changes:")
	for i,(desc,_) in enumerate(actions,1):
		print(f"{i}. {desc}")
	if ns.yes:
		selected=set(range(1,len(actions)+1))
	else:
		ans=input("Apply which changes? [all / none / 1,3,5]: ").strip().lower()
		if ans in {"", "none", "no", "n"}:
			print("No changes applied.")
			return 0
		selected=set(range(1,len(actions)+1)) if ans == "all" else {int(x) for x in ans.split(",") if x.strip().isdigit()}
	for i,(desc,fn) in enumerate(actions,1):
		if i in selected:
			print(f"Applying {i}: {desc}")
			fn()
	print("Done.")
	return 0

if __name__ == "__main__":
	raise SystemExit(main())
