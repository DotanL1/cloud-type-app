import hashlib
import os
import threading
import time


LOCK_DIR = ".\\files\\.locks"
_thread_lock_guard = threading.Lock()
_thread_locks = {}


def _lock_key(owner, file_name, file_type):
    return f"{owner}|{file_name}|{file_type}"


def _lock_path(owner, file_name, file_type):
    os.makedirs(LOCK_DIR, exist_ok=True)
    digest = hashlib.sha256(_lock_key(owner, file_name, file_type).encode("utf-8")).hexdigest()
    return os.path.join(LOCK_DIR, f"{digest}.lock")


class file_guard:
    def __init__(self, owner, file_name, file_type):
        self.owner = owner
        self.file_name = file_name
        self.file_type = file_type
        self.key = _lock_key(owner, file_name, file_type)
        self.path = _lock_path(owner, file_name, file_type)
        self.thread_lock = None

    def __enter__(self):
        with _thread_lock_guard:
            self.thread_lock = _thread_locks.setdefault(self.key, threading.Lock())
        self.thread_lock.acquire()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.close(fd)
                return self
            except FileExistsError:
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        finally:
            if self.thread_lock:
                self.thread_lock.release()
