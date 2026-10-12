"""Application-owned data paths, atomic files and one-time legacy migration."""
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager, closing
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[2]

def home():
    # Explicit data overrides also isolate journals, memories and blobs in tests.
    return Path(os.environ.get('SNAPMIND_HOME') or
                (str(Path(os.environ['SNAPMIND_DATA_DIR']) / 'snapmind')
                 if os.environ.get('SNAPMIND_DATA_DIR') else str(PROJECT / '.snapmind'))).resolve()

def business_path():
    return Path(os.environ['SNAPMIND_DATA_DIR']) / 'snapmind.sqlite3' if os.environ.get('SNAPMIND_DATA_DIR') else home() / 'data/snapmind.sqlite3'

def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode('utf-8') if isinstance(data, str) else data
    if path.exists() and path.read_bytes()==raw:return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name, suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(raw); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)

def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

@contextmanager
def file_lock(path):
    """OS lock shared by API threads and processes; lock file is never unlinked."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if path.stat().st_size == 0: stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        try: yield
        finally:
            stream.seek(0)
            if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream, fcntl.LOCK_UN)

def migrate_legacy(root=None, source_db=None, source_config=None):
    root = Path(root or home())
    source_db = Path(source_db or PROJECT / 'backend/data/snapmind.sqlite3')
    source_config = Path(source_config or PROJECT / 'backend/.snapmind')
    target = root / 'data/snapmind.sqlite3'
    manifest = root / 'backups/legacy/migration.json'
    with file_lock(root / 'thread-writer-locks/migration.lock'):
        done = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
        if done.get('status') == 'complete': return
        folder = manifest.parent; folder.mkdir(parents=True, exist_ok=True)
        report = {'format_version':1, 'status':'staging', 'created_at':datetime.now(timezone.utc).isoformat()}
        if source_db.exists():
            backup = folder / 'snapmind.sqlite3'
            if not backup.exists():
                staged = folder / 'snapmind.sqlite3.tmp'
                with closing(sqlite3.connect(source_db)) as original, closing(sqlite3.connect(staged)) as destination:
                    original.backup(destination)
                os.replace(staged, backup)
            with sqlite3.connect(backup) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise RuntimeError('Legacy database integrity check failed')
                report['tables'] = {name:db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0]
                                    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                known = {'sessions','model_usage','app_settings','ocr_daily_usage','ocr_model_usage','ocr_submission_usage'}
                if set(report['tables']) - known: raise RuntimeError('Unclassified legacy tables; migration stopped without modifying source')
            if target.exists():
                # An interrupted publication is safe to retry; a different destination is not.
                if target.read_bytes() != backup.read_bytes(): raise RuntimeError('Existing destination conflicts with legacy data')
            else: atomic_write(target, backup.read_bytes())
        if source_config.exists():
            raw = source_config.read_bytes()
            backup = folder / 'models.json'; destination = root / 'models.json'
            if backup.exists() and backup.read_bytes() != raw: raise RuntimeError('Legacy configuration changed during migration')
            if destination.exists() and destination.read_bytes() != raw: raise RuntimeError('Existing model configuration conflicts with legacy data')
            json.loads(raw.decode('utf-8-sig'))  # Validate before publication; never log credentials.
            atomic_write(backup, raw)
            if not destination.exists(): atomic_write(destination, raw)
            report['models_sha256'] = hashlib.sha256(raw).hexdigest()
        report['status'] = 'complete'
        atomic_write(manifest, json_text(report)+'\n')

def initialize_paths():
    root = home()
    if not any(os.environ.get(key) for key in ('SNAPMIND_HOME','SNAPMIND_DATA_DIR','SNAPMIND_CONFIG_FILE')):
        migrate_storage_root(PROJECT)
    for directory in ('data/images/local','data/artifacts/local','data/uploads/local','sessions',
                      'memories/local/projects','memories/local/rollout_summaries','backups/state',
                      'backups/business','logs','tmp','cache','thread-writer-locks'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    # Never inspect or migrate real application data into an explicitly isolated environment.
    if not any(os.environ.get(key) for key in ('SNAPMIND_HOME','SNAPMIND_DATA_DIR','SNAPMIND_CONFIG_FILE')):
        migrate_legacy(root)
    return root


def migrate_storage_root(project):
    """Rename the original application data root without merging competing stores."""
    project=Path(project).resolve();old=project/'snapmind';new=project/'.snapmind'
    if old.exists():
        if new.exists():raise RuntimeError('snapmind 与 .snapmind 同时存在，迁移已停止以避免覆盖数据')
        old.rename(new)
    return new
