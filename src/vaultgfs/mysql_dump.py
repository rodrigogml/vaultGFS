from __future__ import annotations
from pathlib import Path
import os, signal, subprocess, tempfile, time
from . import catalog

def cfg_value(defaults, job, key, default=None):
    return job.get(key, defaults.get(key, default))

def mysql_args(mysql_cfg):
    args=[]
    if mysql_cfg.get('socket'):
        args += ['--socket', mysql_cfg['socket']]
    else:
        args += ['--host', mysql_cfg.get('host','localhost'), '--port', str(mysql_cfg.get('port',3306))]
    return args

def defaults_file(mysql_cfg):
    content='[client]\n'
    if mysql_cfg.get('user'):
        content += f"user={mysql_cfg['user']}\n"
    if mysql_cfg.get('password'):
        content += f"password={mysql_cfg['password']}\n"
    f=tempfile.NamedTemporaryFile('w', delete=False)
    f.write(content); f.close(); os.chmod(f.name,0o600)
    return f.name

def limit_prefix(defaults, job):
    cmd=[]
    nice=cfg_value(defaults, job, 'nice', None)
    if nice is not None:
        cmd += ['/usr/bin/nice', '-n', str(int(nice))]
    ionice_class=cfg_value(defaults, job, 'ionice_class', None)
    if ionice_class is not None:
        cmd += ['/usr/bin/ionice', f'-c{int(ionice_class)}']
        ionice_level=cfg_value(defaults, job, 'ionice_level', None)
        if ionice_level is not None and int(ionice_class) in (1,2):
            cmd += [f'-n{int(ionice_level)}']
    return cmd

def process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def ps_metrics(pids):
    alive=[str(p) for p in pids if p and process_alive(p)]
    if not alive:
        return 0.0, 0.0
    r=subprocess.run(['ps','-o','pcpu=,pmem=','-p', ','.join(alive)], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    cpu=0.0; mem=0.0
    for line in r.stdout.splitlines():
        parts=line.split()
        if len(parts) >= 2:
            cpu += float(parts[0]); mem += float(parts[1])
    return cpu, mem

def swap_percent():
    vals={}
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                k,v=line.split(':',1)
                vals[k]=int(v.split()[0])
        total=vals.get('SwapTotal',0); free=vals.get('SwapFree',0)
        if total <= 0:
            return 0.0
        return 100.0 * (total-free) / total
    except Exception:
        return 0.0

def signal_group(proc, sig):
    if proc and proc.pid:
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass

def wait_pipeline(p1, p2, out: Path, defaults, job):
    mode=str(cfg_value(defaults, job, 'resource_monitor', 'passive')).lower()
    if mode not in {'off','passive','active'}:
        mode='passive'
    interval=max(1, int(cfg_value(defaults, job, 'monitor_interval_seconds', 10)))
    pause_seconds=max(1, int(cfg_value(defaults, job, 'pause_seconds', 15)))
    max_pause_cycles=max(0, int(cfg_value(defaults, job, 'max_pause_cycles', 20)))
    abort_sustained=max(interval, int(cfg_value(defaults, job, 'abort_if_sustained_seconds', 300)))
    max_cpu=cfg_value(defaults, job, 'max_cpu_percent', None)
    max_mem=cfg_value(defaults, job, 'max_memory_percent', None)
    max_load=cfg_value(defaults, job, 'max_load_1m', None)
    max_swap=cfg_value(defaults, job, 'max_swap_percent', None)
    max_cpu=float(max_cpu) if max_cpu is not None else None
    max_mem=float(max_mem) if max_mem is not None else None
    max_load=float(max_load) if max_load is not None else None
    max_swap=float(max_swap) if max_swap is not None else None
    sustained=0; pauses=0; last_size=-1
    while p2.poll() is None:
        time.sleep(interval)
        if mode == 'off':
            continue
        cpu, mem = ps_metrics([p1.pid, p2.pid])
        load1=os.getloadavg()[0]
        swp=swap_percent()
        size=out.stat().st_size if out.exists() else 0
        delta=size-last_size if last_size >= 0 else 0
        last_size=size
        print(f"MONITOR job={job['name']} pids={p1.pid},{p2.pid} cpu_percent={cpu:.1f} mem_percent={mem:.1f} load1={load1:.2f} swap_percent={swp:.1f} output_bytes={size} delta_bytes={delta}", flush=True)
        over=False
        if max_cpu is not None and cpu > max_cpu: over=True
        if max_mem is not None and mem > max_mem: over=True
        if max_load is not None and load1 > max_load: over=True
        if max_swap is not None and swp > max_swap: over=True
        if over:
            sustained += interval
            if mode == 'active' and pauses < max_pause_cycles:
                pauses += 1
                print(f"MONITOR_PAUSE job={job['name']} cycle={pauses} seconds={pause_seconds}", flush=True)
                signal_group(p1, signal.SIGSTOP); signal_group(p2, signal.SIGSTOP)
                time.sleep(pause_seconds)
                signal_group(p1, signal.SIGCONT); signal_group(p2, signal.SIGCONT)
            if mode == 'active' and sustained >= abort_sustained:
                signal_group(p1, signal.SIGTERM); signal_group(p2, signal.SIGTERM)
                time.sleep(3)
                signal_group(p1, signal.SIGKILL); signal_group(p2, signal.SIGKILL)
                raise RuntimeError(f"resource limits exceeded for {sustained}s; backup aborted")
        else:
            sustained=0
    e2=p2.stderr.read() if p2.stderr else b''
    e1=p1.stderr.read() if p1.stderr else b''
    rc1=p1.wait(); rc2=p2.returncode
    return rc1, rc2, e1, e2

def run_mysql_job(cfg, job):
    defaults=cfg.get('defaults',{})
    mysql_cfg=cfg.get('mysql',{})
    db=catalog.connect(defaults.get('catalog','/var/lib/vaultgfs/catalog.db'))
    run_id=catalog.start_run(db, job, 'dump')
    dest=Path(job['destination']); dest.mkdir(parents=True, exist_ok=True)
    ts=time.strftime('%Y%m%d-%H%M%S')
    cnf=defaults_file(mysql_cfg)
    outputs=[]; partials=[]
    try:
        level=int(job.get('compression_level', defaults.get('compression_level', 19)))
        threads=int(job.get('compression_threads', defaults.get('compression_threads', 1)))
        if threads < 1:
            threads = 1
        prefix=limit_prefix(defaults, job)
        for schema in job.get('schemas',[]):
            out=dest / f'{schema}-{ts}.sql.zst'
            partials.append(out)
            dump=[*prefix, 'mysqldump', f'--defaults-extra-file={cnf}', *mysql_args(mysql_cfg), '--single-transaction', '--skip-lock-tables', '--routines', '--triggers', '--events', '--set-gtid-purged=OFF', '--no-tablespaces', '--databases', schema]
            zstd=[*prefix, 'zstd', f'-T{threads}', '-o', str(out)]
            if int(level) > 19:
                zstd.append('--ultra')
            zstd.append(f'-{level}')
            print(f"START mysql dump job={job['name']} schema={schema} compression_level={level} compression_threads={threads} monitor={cfg_value(defaults, job, 'resource_monitor', 'passive')}", flush=True)
            p1=subprocess.Popen(dump, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)
            p2=subprocess.Popen(zstd, stdin=p1.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, preexec_fn=os.setsid)
            p1.stdout.close()
            rc1, rc2, e1, e2 = wait_pipeline(p1, p2, out, defaults, job)
            if rc1 or rc2:
                raise RuntimeError(f'mysqldump/zstd failed for {schema}: rc dump={rc1} zstd={rc2} {e1.decode(errors="replace")} {e2.decode(errors="replace")}')
            outputs.append(str(out))
        catalog.finish_run(db, run_id, 'success', str(dest), None, f'dumped {len(outputs)} schema(s)')
        print(f"SUCCESS {job['name']}: dumped {len(outputs)} schema(s) -> {dest}")
        return 0
    except BaseException as e:
        for p in partials:
            try:
                if p.exists() and str(p) not in outputs:
                    p.unlink()
            except FileNotFoundError:
                pass
        catalog.finish_run(db, run_id, 'failed', str(dest), None, str(e))
        raise
    finally:
        try: os.unlink(cnf)
        except FileNotFoundError: pass
