from __future__ import annotations
from pathlib import Path
import hashlib, json, subprocess, time
from . import catalog

def sha256_file(path: Path, buf=1024*1024):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(buf), b''):
            h.update(b)
    return h.hexdigest()

def scan(source: Path):
    rows=[]
    for p in source.rglob('*'):
        try:
            if not p.is_file() or p.is_symlink():
                continue
            st=p.stat()
            rows.append((str(p.relative_to(source)), st.st_size, st.st_mtime_ns, st.st_mode, st.st_uid, st.st_gid))
        except FileNotFoundError:
            continue
    rows.sort(key=lambda x:x[0])
    return rows

def changed_rows(db, job, level, current):
    if level == 'full':
        return current
    base = catalog.last_success_run(db, job['name'], 'full' if level == 'diff' else None)
    if not base:
        return current
    old = catalog.snapshot_map(db, base['id'])
    out=[]
    for r in current:
        rel,size,mtime_ns,*_=r
        o=old.get(rel)
        if o is None or int(o['size']) != size or int(o['mtime_ns']) != mtime_ns:
            out.append(r)
    return out

def make_archive(source, destdir, backup_id, cls, rels, level, threads):
    if not rels:
        return None

    listfile = destdir / f'{backup_id}.{cls}.list0'

    with listfile.open('wb') as f:
        for rel in rels:
            f.write(rel.encode('utf-8') + b'\0')

    if cls == 'storage':
        out = destdir / f'{backup_id}.storage.tar'
        cmd = ['tar', '--null', '-C', str(source), '-cf', str(out), '-T', str(listfile)]
    else:
        out = destdir / f'{backup_id}.compressible.tar.zst'
        zopt = f'zstd -T{threads} ' + ('--ultra ' if int(level) > 19 else '') + f'-{level}'
        cmd = ['tar', '--null', '-C', str(source), '--use-compress-program', zopt, '-cf', str(out), '-T', str(listfile)]

    subprocess.run(cmd, check=True)
    listfile.unlink(missing_ok=True)
    return str(out)

def run_filesystem_job(cfg, job, level):
    defaults=cfg.get('defaults',{})
    db=catalog.connect(defaults.get('catalog','/var/lib/vaultgfs/catalog.db'))
    run_id=catalog.start_run(db, job, level)
    source=Path(job['source'])
    backup_id=f"{job['name']}-{level}-{time.strftime('%Y%m%d-%H%M%S')}"
    destdir=Path(job['destination']) / level / backup_id
    try:
        current=scan(source)
        selected=changed_rows(db, job, level, current)
        if job.get('skip_if_unchanged', False) and not selected:
            catalog.finish_run(db, run_id, 'skipped', str(destdir), None, 'no changes detected')
            print(f"SKIPPED {job['name']} {level}: no changes detected")
            return 0
        destdir.mkdir(parents=True, exist_ok=True)
        storage_exts=set(defaults.get('storage_extensions', []))
        clevel=int(job.get('compression_level', defaults.get('compression_level', 19)))
        threads=int(job.get('compression_threads', defaults.get('compression_threads', 0)))
        if threads < 1:
            threads = 1
        selected_set={r[0] for r in selected}
        storage=[]; compressible=[]; files=[]; snaps=[]
        for rel,size,mtime_ns,mode,uid,gid in current:
            cls=None; digest=None
            if rel in selected_set:
                cls='storage' if Path(rel).suffix.lower() in storage_exts else 'compressible'
                digest=sha256_file(source/rel)
                (storage if cls=='storage' else compressible).append(rel)
                files.append({'path':rel,'size':size,'mtime_ns':mtime_ns,'mode':mode,'uid':uid,'gid':gid,'sha256':digest,'class':cls})
            snaps.append((run_id, job['name'], rel, size, mtime_ns, mode, uid, gid, digest, cls))
        archives=[]
        for cls, rels in [('storage',storage),('compressible',compressible)]:
            a=make_archive(source,destdir,backup_id,cls,rels,clevel,threads)
            if a: archives.append(a)
        manifest={'backup_id':backup_id,'job':job['name'],'type':job['type'],'level':level,'source':str(source),'created_at':int(time.time()),'archives':archives,'files':files}
        mp=destdir/'manifest.json'
        mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        catalog.insert_snapshots(db, snaps)
        catalog.finish_run(db, run_id, 'success', str(destdir), str(mp), f'{len(selected)} files selected')
        print(f"SUCCESS {job['name']} {level}: {len(selected)} files -> {destdir}")
        return 0
    except Exception as e:
        catalog.finish_run(db, run_id, 'failed', str(destdir), None, str(e))
        raise
