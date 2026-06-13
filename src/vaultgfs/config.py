from __future__ import annotations
from pathlib import Path
import tomllib

DEFAULT_CONFIG = "/opt/vaultGFS/config.toml"
SYSTEM_SCHEMAS = {"mysql", "information_schema", "performance_schema", "sys"}

class ConfigError(Exception):
	pass

def load_config(path: str | Path = DEFAULT_CONFIG) -> dict:
	p = Path(path)
	with p.open("rb") as f:
		cfg = tomllib.load(f)
	cfg.setdefault("defaults", {})
	cfg.setdefault("jobs", [])
	for job in cfg["jobs"]:
		job.setdefault("enabled", True)
		job.setdefault("skip_if_unchanged", False)
	return cfg

def validate_config(cfg: dict) -> list[str]:
	errors=[]
	names=set()
	for i, job in enumerate(cfg.get("jobs", []), 1):
		name=job.get("name")
		typ=job.get("type")
		if not name:
			errors.append(f"job #{i}: missing name")
		elif name in names:
			errors.append(f"job {name}: duplicate name")
		else:
			names.add(name)
		if typ not in {"filesystem-gfs", "mysql-dump"}:
			errors.append(f"job {name}: invalid type {typ!r}")
		if typ == "filesystem-gfs":
			for k in ("source","destination","schedule_full","schedule_diff","schedule_inc"):
				if not job.get(k):
					errors.append(f"job {name}: missing {k}")
		if typ == "mysql-dump":
			if not job.get("schemas"):
				errors.append(f"job {name}: missing schemas")
			if not job.get("destination"):
				errors.append(f"job {name}: missing destination")
			if not job.get("schedule"):
				errors.append(f"job {name}: missing schedule")
			for s in job.get("schemas", []):
				if s in SYSTEM_SCHEMAS:
					errors.append(f"job {name}: system schema not allowed: {s}")
	return errors
