import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

_jobs = {}
_lock = threading.Lock()
# GPU-bound work (music generation, stems) is serialized; light work runs in parallel.
_gpu = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gpu")
_cpu = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cpu")


class Job:
    def __init__(self, kind, label):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.label = label
        self.status = "queued"
        self.progress = 0.0
        self.message = "Queued"
        self.track_ids = []
        self.result = None
        self.error = None
        self.created_at = time.time()
        self.finished_at = None

    def update(self, progress=None, message=None):
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))
        if message is not None:
            self.message = message

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message,
            "track_ids": list(self.track_ids),
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


def submit(kind, label, fn, gpu=True):
    job = Job(kind, label)
    with _lock:
        _jobs[job.id] = job

    def run():
        job.status = "running"
        job.message = "Working"
        try:
            out = fn(job)
            if out is not None:
                job.result = out
            job.status = "succeeded"
            job.progress = 1.0
            job.message = "Done"
        except Exception as e:  # noqa: BLE001 - surfaced to the UI
            traceback.print_exc()
            job.status = "failed"
            job.error = str(e) or e.__class__.__name__
            job.message = "Failed"
        finally:
            job.finished_at = time.time()

    (_gpu if gpu else _cpu).submit(run)
    return job


def get(job_id):
    return _jobs.get(job_id)


def recent(limit=50):
    with _lock:
        items = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return [j.to_dict() for j in items[:limit]]
