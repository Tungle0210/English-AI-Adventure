"""Private, checksummed offline data transfer. Never overwrites a populated target."""
import argparse,hashlib,json,os,shutil,sqlite3,tempfile,uuid,zipfile
from pathlib import Path,PurePosixPath
from contextlib import closing

DB='adventure.sqlite3'

def digest(stream):
    h=hashlib.sha256()
    for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def db_summary(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity check failed')
        return {name:c.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('lessons','attempts','cache')}

def export_data(data,output,offline=False):
    data=Path(data).resolve();output=Path(output).resolve()
    if not offline:raise ValueError('Stop all writers/enable maintenance, then pass --offline to confirm')
    if output==data or data in output.parents:raise ValueError('Backup output must be outside the data directory')
    if output.exists():raise ValueError('Output already exists; use a new filename')
    if not (data/DB).is_file() or not (data/'teacher-access.txt').is_file():raise ValueError('Missing real database or teacher-access.txt')
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest={'format':1,'database':{},'files':[]}
    with tempfile.TemporaryDirectory(prefix='adventure-snapshot-',dir=output.parent) as temp:
        snapshot=Path(temp)/DB
        with closing(sqlite3.connect((data/DB).as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(snapshot)) as dst:src.backup(dst)
        manifest['database']=db_summary(snapshot)
        partial=Path(temp)/'bundle.zip'
        with zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
            entries=[p for p in data.rglob('*') if p.is_file() and p.name not in (DB,DB+'-wal',DB+'-shm','.runtime.lock')]
            entries.append(snapshot)
            for p in entries:
                if p.is_symlink():raise ValueError('Symlinks are not supported in private bundles')
                name=DB if p==snapshot else p.relative_to(data).as_posix()
                if p.name=='.env' or p.name.startswith('.env.'):raise ValueError('Refusing to package environment secrets')
                with p.open('rb') as f:sha=digest(f)
                manifest['files'].append({'path':name,'bytes':p.stat().st_size,'sha256':sha})
                archive.write(p,name)
            archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        # Exclusive creation never overwrites another backup. Verify before using a bundle.
        with output.open('xb') as dst,partial.open('rb') as src:shutil.copyfileobj(src,dst,1024*1024)
    return {'files':len(manifest['files']),'database':manifest['database'],'bytes':output.stat().st_size}

def inspect_bundle(bundle,into=None):
    bundle=Path(bundle).resolve();target=Path(into).resolve() if into else None
    if target and target.exists() and any(target.iterdir()):raise ValueError('Target is not empty; restore to a NEW directory, never overwrite live data')
    if target and target in bundle.parents:raise ValueError('Bundle must be outside the target')
    staging=None
    try:
        with zipfile.ZipFile(bundle) as archive:
            names=archive.namelist()
            if len(names)!=len(set(names)) or len(names)>100000:raise ValueError('Invalid duplicate/excess archive entries')
            if sum(i.file_size for i in archive.infolist())>16*1024**3:raise ValueError('Archive exceeds 16 GiB uncompressed; review disk capacity')
            for info in archive.infolist():
                path=PurePosixPath(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename or str(path)!=info.filename or ((info.external_attr>>16)&0o170000)==0o120000:raise ValueError('Unsafe archive path')
            if DB not in names or 'teacher-access.txt' not in names:raise ValueError('Missing database or teacher access file')
            manifest=json.loads(archive.read('manifest.json'))
            if manifest.get('format')!=1:raise ValueError('Unsupported bundle format')
            entries=manifest['files']
            if set(names)!={e['path'] for e in entries}|{'manifest.json'}:raise ValueError('Manifest does not match archive')
            if target:
                target.parent.mkdir(parents=True,exist_ok=True)
                staging=target.parent/(target.name+'.import-'+uuid.uuid4().hex);staging.mkdir()
            for entry in entries:
                info=archive.getinfo(entry['path'])
                if info.file_size!=entry['bytes']:raise ValueError('Manifest size mismatch')
                with archive.open(info) as stream:
                    if digest(stream)!=entry['sha256']:raise ValueError('Checksum mismatch')
                if staging:
                    dest=staging/entry['path'];dest.parent.mkdir(parents=True,exist_ok=True)
                    with archive.open(info) as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            if staging:
                summary=db_summary(staging/DB)
                if summary!=manifest['database']:raise ValueError('Database row counts mismatch')
                if not (staging/'teacher-access.txt').is_file():raise ValueError('Missing teacher access code')
                if target.exists():target.rmdir() # Only an empty target is accepted above; rmdir refuses changed/nonempty targets.
                staging.rename(target);staging=None
            if not target:
                with tempfile.TemporaryDirectory(prefix='adventure-verify-',dir=bundle.parent) as temp:
                    dbfile=Path(temp)/DB
                    with archive.open(DB) as src,dbfile.open('wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
                    if db_summary(dbfile)!=manifest['database']:raise ValueError('Database row counts mismatch')
            return {'status':'PASS','files':len(entries),'database':manifest['database']}
    finally:
        if staging and staging.exists():
            # This is only the newly created staging directory, never the user's existing target.
            shutil.rmtree(staging)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='action',required=True)
    p=subs.add_parser('export');p.add_argument('--data',required=True);p.add_argument('--output',required=True);p.add_argument('--offline',action='store_true')
    p=subs.add_parser('verify');p.add_argument('--bundle',required=True)
    p=subs.add_parser('import');p.add_argument('--bundle',required=True);p.add_argument('--into',required=True)
    args=parser.parse_args()
    try:
        result=export_data(args.data,args.output,args.offline) if args.action=='export' else inspect_bundle(args.bundle,args.into if args.action=='import' else None)
        print(json.dumps(result,ensure_ascii=True))
    except (ValueError,OSError,zipfile.BadZipFile,sqlite3.Error,KeyError) as error:
        raise SystemExit('FAILED: '+str(error))
