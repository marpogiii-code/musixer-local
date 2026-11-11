"""Client for a local ACE-Step 1.5 API server (python -m acestep.api_server)."""
import json
import time
from pathlib import Path

import httpx

from ..config import load_settings


class AceStepError(RuntimeError):
    pass


def _base():
    s = load_settings()
    headers = {}
    if s.get("acestep_api_key"):
        headers["Authorization"] = f"Bearer {s['acestep_api_key']}"
    return s["acestep_url"].rstrip("/"), headers


def _unwrap(resp):
    try:
        body = resp.json()
    except ValueError:
        raise AceStepError(f"ACE-Step returned HTTP {resp.status_code}: {resp.text[:300]}")
    if resp.status_code >= 400 or (isinstance(body, dict) and body.get("code", 200) != 200):
        err = body.get("error") or body.get("detail") if isinstance(body, dict) else body
        raise AceStepError(f"ACE-Step error: {err}")
    return body.get("data") if isinstance(body, dict) and "data" in body else body


def health(timeout=2.0):
    url, headers = _base()
    try:
        r = httpx.get(f"{url}/health", headers=headers, timeout=timeout)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def models():
    url, headers = _base()
    try:
        data = _unwrap(httpx.get(f"{url}/v1/models", headers=headers, timeout=5))
        return data or {}
    except (httpx.HTTPError, AceStepError):
        return {}


def format_input(prompt, lyrics, params=None, temperature=0.85):
    url, headers = _base()
    payload = {"prompt": prompt, "lyrics": lyrics, "temperature": temperature, "param_obj": json.dumps(params or {})}
    return _unwrap(httpx.post(f"{url}/format_input", json=payload, headers=headers, timeout=300))


def random_sample(kind="custom_mode"):
    url, headers = _base()
    return _unwrap(httpx.post(f"{url}/create_random_sample", json={"sample_type": kind}, headers=headers, timeout=30))


def _form_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v)


def release(params, files=None):
    """Submit a task. Audio inputs are uploaded as multipart so remote servers work too."""
    url, headers = _base()
    params = {k: v for k, v in params.items() if v is not None}
    if files:
        handles = {}
        try:
            for field, path in files.items():
                handles[field] = (Path(path).name, open(path, "rb"))
            data = {k: _form_value(v) for k, v in params.items()}
            r = httpx.post(f"{url}/release_task", data=data, files=handles, headers=headers, timeout=300)
        finally:
            for _, fh in handles.values():
                fh.close()
    else:
        r = httpx.post(f"{url}/release_task", json=params, headers=headers, timeout=60)
    data = _unwrap(r)
    task_id = (data or {}).get("task_id")
    if not task_id:
        raise AceStepError(f"ACE-Step did not return a task id: {data}")
    return task_id


def query(task_id):
    url, headers = _base()
    data = _unwrap(httpx.post(f"{url}/query_result", json={"task_id_list": [task_id]}, headers=headers, timeout=30))
    return data[0] if data else None


def download(file_url, dst):
    url, headers = _base()
    full = file_url if file_url.startswith("http") else f"{url}{file_url}"
    with httpx.stream("GET", full, headers=headers, timeout=300) as r:
        if r.status_code != 200:
            raise AceStepError(f"Download failed with HTTP {r.status_code}")
        with open(dst, "wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)
    return Path(dst)


def run_task(job, params, files=None, out_dir=None, poll=1.5, timeout=3600):
    """Submit, poll until finished and download all generated audio. Returns list of (path, item)."""
    job.update(0.03, "Sending to ACE-Step")
    task_id = release(params, files)
    started = time.time()
    while True:
        if time.time() - started > timeout:
            raise AceStepError("ACE-Step task timed out")
        info = query(task_id) or {}
        status = info.get("status", 0)
        if status == 1:
            break
        if status == 2:
            raise AceStepError(f"ACE-Step generation failed: {_extract_error(info)}")
        elapsed = time.time() - started
        msg = info.get("progress_text") or info.get("stage") or "Generating music"
        prog = info.get("progress")
        job.update(float(prog) * 0.9 if isinstance(prog, (int, float)) and prog <= 1 else min(0.9, 0.05 + elapsed / 120), str(msg)[:120])
        time.sleep(poll)
    items = info.get("result")
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except ValueError:
            items = []
    items = items or []
    out = []
    out_dir = Path(out_dir)
    job.update(0.92, "Downloading audio")
    for i, item in enumerate(items):
        f = item.get("file") or item.get("url")
        if not f:
            continue
        suffix = Path(f.split("path=")[-1].split("&")[0]).suffix or ".mp3"
        if "%2E" in suffix or len(suffix) > 6:
            suffix = "." + params.get("audio_format", "mp3")
        dst = out_dir / f"{job.id}_{i}{suffix}"
        download(f, dst)
        out.append((dst, item))
    if not out:
        raise AceStepError("ACE-Step finished but returned no audio")
    return out


def _extract_error(info):
    res = info.get("result")
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except ValueError:
            return res[:300]
    if isinstance(res, list) and res:
        return res[0].get("error") or res[0].get("generation_info") or "unknown error"
    return info.get("error") or "unknown error"
