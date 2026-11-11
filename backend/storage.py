"""OS lock: a disk-backed SQLite application must have exactly one writer process."""
from contextlib import contextmanager
import os

@contextmanager
def single_writer(data):
    data.mkdir(parents=True,exist_ok=True)
    handle=(data/'.runtime.lock').open('a+b')
    try:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise RuntimeError('Another process owns ADVENTURE_DATA_DIR; stop it or choose a separate data directory') from None
        yield
    finally:handle.close()
