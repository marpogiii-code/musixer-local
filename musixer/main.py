import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, audio, jobs, services, store, writing
from .config import PERSONA_DIR, UPLOAD_DIR, WEB_DIR, public_settings, save_settings
from .engines import acestep, tts

app = FastAPI(title="Musixer Local", version=__version__)
MAX_UPLOAD = 200 * 1024 * 1024
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac", ".mp4", ".webm"}


def _track(tid):
    t = store.get("tracks", tid)
    if not t:
        raise HTTPException(404, "Track not found")
    return t


def _public(t):
    t = dict(t)
    t["audio_url"] = f"/media/audio/{Path(t['audio_path']).name}"
    t["cover_url"] = f"/media/cover/{Path(t['cover_path']).name}" if t.get("cover_path") else ""
    t["has_video"] = bool(t.get("video_path")) and Path(t["video_path"]).exists()
    for k in ("audio_path", "cover_path", "video_path"):
        t.pop(k, None)
    return t


def _job(job):
    return job.to_dict()


@app.exception_handler(ValueError)
async def _value_error(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


# ---------------------------------------------------------------- status / settings

@app.get("/api/status")
def status():
    return {"version": __version__, **services.status()}


@app.get("/api/settings")
def get_settings():
    return public_settings()


@app.put("/api/settings")
def put_settings(patch: Dict[str, Any] = Body(...)):
    save_settings(patch)
    return public_settings()


# ---------------------------------------------------------------- jobs

@app.get("/api/jobs")
def list_jobs():
    return jobs.recent()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return _job(j)


# ---------------------------------------------------------------- create

@app.post("/api/generate")
def generate(req: Dict[str, Any] = Body(...)):
    label = req.get("title") or (req.get("description") or req.get("style") or "New song")[:60]
    return _job(jobs.submit("song", label, lambda j: services.generate_song(j, req)))


@app.post("/api/uploads")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in AUDIO_EXT | {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, f"Unsupported file type {ext}")
    uid = store.new_id()
    dst = UPLOAD_DIR / f"{uid}{ext}"
    size = 0
    with open(dst, "wb") as fh:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD:
                fh.close()
                dst.unlink(missing_ok=True)
                raise HTTPException(413, "File too large (max 200 MB)")
            fh.write(chunk)
    dur = audio.duration(dst) if ext in AUDIO_EXT else 0
    return {"id": uid, "name": file.filename, "duration": dur, "url": f"/media/upload/{dst.name}"}


@app.post("/api/library/upload")
async def library_upload(file: UploadFile = File(...), title: str = Form("")):
    up = await upload(file)
    src = next(UPLOAD_DIR.glob(f"{up['id']}.*"))
    if src.suffix.lower() not in AUDIO_EXT:
        raise HTTPException(400, "Upload an audio file")
    t = services.import_upload(src, title or Path(file.filename or "Upload").stem)
    return _public(t)


# ---------------------------------------------------------------- library

@app.get("/api/tracks")
def list_tracks(q: str = "", kind: str = "", album_id: str = "", favorite: bool = False, persona_id: str = ""):
    where, args = [], []
    if q:
        where.append("(title LIKE ? OR style LIKE ? OR lyrics LIKE ?)")
        args += [f"%{q}%"] * 3
    if kind:
        where.append("kind = ?")
        args.append(kind)
    if album_id:
        where.append("album_id = ?")
        args.append(album_id)
    if persona_id:
        where.append("persona_id = ?")
        args.append(persona_id)
    if favorite:
        where.append("favorite = 1")
    return [_public(t) for t in store.query("tracks", " AND ".join(where), args)]


@app.get("/api/tracks/{tid}")
def get_track(tid: str):
    return _public(_track(tid))


@app.patch("/api/tracks/{tid}")
def patch_track(tid: str, patch: Dict[str, Any] = Body(...)):
    _track(tid)
    allowed = {k: v for k, v in patch.items() if k in {"title", "style", "lyrics", "favorite", "album_id", "persona_id"}}
    if "favorite" in allowed:
        allowed["favorite"] = 1 if allowed["favorite"] else 0
    return _public(store.update("tracks", tid, allowed))


@app.delete("/api/tracks/{tid}")
def delete_track(tid: str):
    t = _track(tid)
    for k in ("audio_path", "cover_path", "video_path"):
        if t.get(k):
            Path(t[k]).unlink(missing_ok=True)
    store.delete("tracks", tid)
    return {"ok": True}


@app.get("/api/tracks/{tid}/peaks")
def track_peaks(tid: str, n: int = 160):
    return audio.peaks(_track(tid)["audio_path"], max(20, min(1000, n)))


@app.post("/api/tracks/{tid}/cover")
async def track_cover(tid: str, file: UploadFile = File(...)):
    t = _track(tid)
    from PIL import Image
    img = Image.open(file.file).convert("RGB")
    side = min(img.size)
    img = img.crop(((img.width - side) // 2, (img.height - side) // 2, (img.width + side) // 2, (img.height + side) // 2)).resize((768, 768))
    img.save(t["cover_path"], quality=92)
    return _public(t)


@app.post("/api/tracks/{tid}/remix")
def track_remix(tid: str, req: Dict[str, Any] = Body(...)):
    t = _track(tid)
    label = f"{services.REMIX_LABELS.get(req.get('op'), 'Remix')}: {t['title']}"
    return _job(jobs.submit("remix", label, lambda j: services.remix(j, t, req)))


@app.post("/api/tracks/{tid}/fade")
def track_fade(tid: str, req: Dict[str, Any] = Body(...)):
    t = _track(tid)
    return _job(jobs.submit("fade", f"Fade: {t['title']}", lambda j: services.fade(j, t, req), gpu=False))


@app.post("/api/tracks/{tid}/separate")
def track_separate(tid: str, req: Dict[str, Any] = Body(default={})):
    t = _track(tid)
    return _job(jobs.submit("stems", f"Stems: {t['title']}", lambda j: services.separate(j, t, req)))


@app.post("/api/tracks/{tid}/video")
def track_video(tid: str, req: Dict[str, Any] = Body(default={})):
    t = _track(tid)
    return _job(jobs.submit("video", f"Video: {t['title']}", lambda j: services.render_video(j, t, req), gpu=False))


@app.get("/api/tracks/{tid}/download")
def track_download(tid: str, format: str = "mp3"):
    t = _track(tid)
    fmt = format.lower()
    if fmt not in {"mp3", "m4a", "wav", "flac", "mp4"}:
        raise HTTPException(400, "Unsupported format")
    try:
        path = services.export(t, fmt)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    safe = re.sub(r"[^\w\- ()\[\]+]", "", t["title"]).strip() or "track"
    return FileResponse(path, filename=f"{safe}.{fmt}")


# ---------------------------------------------------------------- albums & personas

@app.get("/api/albums")
def list_albums():
    out = []
    for a in store.query("albums"):
        a["count"] = len(store.query("tracks", "album_id = ?", (a["id"],)))
        out.append(a)
    return out


@app.post("/api/albums")
def create_album(req: Dict[str, Any] = Body(...)):
    if not (req.get("name") or "").strip():
        raise HTTPException(400, "Album name is required")
    return store.insert("albums", {"name": req["name"].strip(), "description": req.get("description", "")})


@app.patch("/api/albums/{aid}")
def patch_album(aid: str, req: Dict[str, Any] = Body(...)):
    return store.update("albums", aid, {k: v for k, v in req.items() if k in ("name", "description")})


@app.delete("/api/albums/{aid}")
def delete_album(aid: str):
    for t in store.query("tracks", "album_id = ?", (aid,)):
        store.update("tracks", t["id"], {"album_id": None})
    store.delete("albums", aid)
    return {"ok": True}


@app.get("/api/personas")
def list_personas():
    return [{**p, "has_voice": bool(p.get("reference_path")), "reference_path": None} for p in store.query("personas")]


@app.post("/api/personas")
def create_persona(req: Dict[str, Any] = Body(...)):
    label = f"Persona: {req.get('name') or 'new'}"
    return _job(jobs.submit("persona", label, lambda j: services.make_persona(j, req), gpu=bool(req.get("isolate_vocals"))))


@app.patch("/api/personas/{pid}")
def patch_persona(pid: str, req: Dict[str, Any] = Body(...)):
    if not store.get("personas", pid):
        raise HTTPException(404, "Persona not found")
    p = store.update("personas", pid, {k: v for k, v in req.items() if k in ("name", "style", "vocal_gender", "notes")})
    return {**p, "has_voice": bool(p.get("reference_path")), "reference_path": None}


@app.get("/api/personas/{pid}/voice")
def persona_voice(pid: str):
    p = store.get("personas", pid)
    if not p or not p.get("reference_path") or not Path(p["reference_path"]).exists():
        raise HTTPException(404, "This persona has no voice clip")
    return FileResponse(p["reference_path"])


@app.delete("/api/personas/{pid}")
def delete_persona(pid: str):
    p = store.get("personas", pid)
    if p and p.get("reference_path", "").startswith(str(PERSONA_DIR)):
        Path(p["reference_path"]).unlink(missing_ok=True)
    store.delete("personas", pid)
    return {"ok": True}


# ---------------------------------------------------------------- writing tools

@app.post("/api/write/song")
def write_song(req: Dict[str, Any] = Body(...)):
    out = writing.write_song(req.get("description", ""), bool(req.get("instrumental")), req.get("language", "English"), req.get("style", ""))
    if out is None:
        d = req.get("description", "")
        out = {"title": writing._offline_title(d), "style": req.get("style") or writing.random_style(),
               "lyrics": "[Instrumental]" if req.get("instrumental") else writing.offline_lyrics(d), "source": "offline"}
    return out


@app.post("/api/write/enhance-style")
def enhance_style(req: Dict[str, Any] = Body(...)):
    return {"style": writing.enhance_style(req.get("style", ""))}


@app.get("/api/write/random-style")
def random_style():
    return {"style": writing.random_style()}


@app.post("/api/write/style")
def guided_style(req: Dict[str, Any] = Body(...)):
    keys = ("genre", "subgenre", "era", "instruments", "mood", "tempo", "complexity", "custom")
    return {"style": writing.guided_style(**{k: req.get(k, "" if k != "complexity" else 50) for k in keys})}


@app.post("/api/write/lyrics")
def gen_lyrics(req: Dict[str, Any] = Body(...)):
    keys = ("genre", "mood", "structure", "language", "rhyme")
    return {"lyrics": writing.generate_lyrics(req.get("idea", ""), **{k: req[k] for k in keys if req.get(k)})}


@app.post("/api/write/studio")
def studio(req: Dict[str, Any] = Body(...)):
    items, source = writing.studio(req.get("action", "next_line"), req.get("lyrics", ""), req.get("selection", ""),
                                   req.get("before", ""), req.get("after", ""), req.get("idea", ""))
    return {"suggestions": items, "source": source}


@app.post("/api/write/speech")
def speech_script(req: Dict[str, Any] = Body(...)):
    return writing.speech_script(req.get("description", ""), req.get("preset", "voiceover"), req.get("length", "short"))


@app.post("/api/write/format")
def ace_format(req: Dict[str, Any] = Body(...)):
    """ACE-Step's own 5Hz LM formatter (caption + lyrics + metadata)."""
    return acestep.format_input(req.get("style", ""), req.get("lyrics", ""), {"language": req.get("language", "en")})


@app.get("/api/lyric-docs")
def list_docs():
    return store.query("lyric_docs", order="updated_at DESC")


@app.post("/api/lyric-docs")
def create_doc(req: Dict[str, Any] = Body(...)):
    return store.insert("lyric_docs", {k: req.get(k, "") for k in ("title", "idea", "content")} | {"versions": []})


@app.put("/api/lyric-docs/{did}")
def save_doc(did: str, req: Dict[str, Any] = Body(...)):
    doc = store.get("lyric_docs", did)
    if not doc:
        raise HTTPException(404, "Draft not found")
    patch = {k: req[k] for k in ("title", "idea", "content") if k in req}
    if req.get("snapshot") and doc["content"].strip():
        versions = (doc.get("versions") or [])[-29:] + [{"content": doc["content"], "at": doc["updated_at"]}]
        patch["versions"] = versions
    return store.update("lyric_docs", did, patch)


@app.delete("/api/lyric-docs/{did}")
def delete_doc(did: str):
    store.delete("lyric_docs", did)
    return {"ok": True}


# ---------------------------------------------------------------- speech

@app.get("/api/tts/voices")
def voices():
    return {"voices": tts.VOICES, "presets": writing.SPEECH_PRESETS, "available": tts.available()}


@app.post("/api/speech")
def create_speech(req: Dict[str, Any] = Body(...)):
    label = (req.get("title") or req.get("description") or req.get("script") or "Spoken track")[:60]
    return _job(jobs.submit("speech", label, lambda j: services.speech(j, req)))


# ---------------------------------------------------------------- media & web

def _media(base, name):
    from .config import AUDIO_DIR, COVER_DIR
    root = {"audio": AUDIO_DIR, "cover": COVER_DIR, "upload": UPLOAD_DIR}[base]
    p = (root / Path(name).name)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/media/{base}/{name}")
def media(base: str, name: str):
    if base not in {"audio", "cover", "upload"}:
        raise HTTPException(404)
    return _media(base, name)


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


def run(host: Optional[str] = None, port: Optional[int] = None):
    import os

    import uvicorn
    uvicorn.run(app, host=host or os.environ.get("MUSIXER_HOST", "127.0.0.1"), port=int(port or os.environ.get("MUSIXER_PORT", 7870)))


if __name__ == "__main__":
    run()
