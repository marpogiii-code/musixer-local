"""Core workflows: song generation, remixing, stems, fades, videos and spoken tracks."""
import random
import re
import shutil
from pathlib import Path

from . import audio, store, writing
from .config import AUDIO_DIR, COVER_DIR, EXPORT_DIR, PERSONA_DIR, TMP_DIR, UPLOAD_DIR, load_settings
from .engines import acestep, llm, mock, stems, tts

MAX_DURATION = 600


def engine_name():
    return load_settings().get("music_engine", "acestep")


def _caption(style, vocal_gender="auto", instrumental=False, extra=""):
    parts = [style.strip().rstrip(",")] if style and style.strip() else []
    if instrumental:
        parts.append("instrumental, no vocals")
    elif vocal_gender in ("male", "female"):
        parts.append(f"{vocal_gender} vocals")
    if extra:
        parts.append(extra)
    return ", ".join(p for p in parts if p)


def _knobs(weirdness, style_influence):
    w = max(0, min(100, int(weirdness if weirdness is not None else 50)))
    si = max(0, min(100, int(style_influence if style_influence is not None else 50)))
    return {
        "lm_temperature": round(0.6 + w / 100 * 0.6, 3),
        "infer_method": "sde" if w >= 75 else "ode",
        "guidance_scale": round(3.0 + si / 100 * 9.0, 2),
        "lm_cfg_scale": round(1.5 + si / 100 * 2.0, 2),
    }


def _resolve_upload(upload_id):
    if not upload_id:
        return None
    hits = list(UPLOAD_DIR.glob(f"{Path(upload_id).name}.*"))
    return hits[0] if hits else None


def _save_track(src, *, title, kind, style="", lyrics="", params=None, metas=None, parent_id=None,
                persona_id=None, album_id=None, engine=""):
    tid = store.new_id()
    src = Path(src)
    dst = AUDIO_DIR / f"{tid}{src.suffix.lower() or '.mp3'}"
    shutil.move(str(src), dst)
    cover = COVER_DIR / f"{tid}.jpg"
    parent = store.get("tracks", parent_id) if parent_id else None
    if parent and parent.get("cover_path") and Path(parent["cover_path"]).exists() and kind not in ("song",):
        shutil.copy(parent["cover_path"], cover)
    else:
        audio.make_cover(cover, title, style)
    return store.insert("tracks", {
        "id": tid, "title": title or "Untitled", "kind": kind, "style": style or "", "lyrics": lyrics or "",
        "params": params or {}, "metas": metas or {}, "audio_path": str(dst), "cover_path": str(cover),
        "duration": audio.duration(dst), "parent_id": parent_id, "persona_id": persona_id,
        "album_id": album_id, "engine": engine,
    })


def _ace_common(s, req, model=None):
    p = {
        "thinking": bool(s.get("acestep_thinking", True)),
        "inference_steps": int(req.get("steps") or s.get("acestep_steps", 8)),
        "batch_size": int(req.get("batch_size") or s.get("batch_size", 2)),
        "audio_format": req.get("format") if req.get("format") in ("mp3", "wav", "flac") else "mp3",
        "vocal_language": req.get("language") or "en",
        "model": model or req.get("model") or None,
    }
    seed = req.get("seed")
    if seed not in (None, "", -1, "-1"):
        p["use_random_seed"] = False
        p["seed"] = int(seed)
    return p


def _version_titles(title, n):
    return [title if n == 1 else f"{title} (v{i + 1})" for i in range(n)]


# ---------------------------------------------------------------- create


def generate_song(job, req):
    s = load_settings()
    engine = s.get("music_engine", "acestep")
    persona = store.get("personas", req["persona_id"]) if req.get("persona_id") else None
    instrumental = bool(req.get("instrumental"))
    vocal_gender = req.get("vocal_gender") or (persona or {}).get("vocal_gender") or "auto"
    style = (req.get("style") or "").strip()
    if persona and persona.get("style") and persona["style"] not in style:
        style = ", ".join(x for x in (style, persona["style"]) if x)
    lyrics = (req.get("lyrics") or "").strip()
    title = (req.get("title") or "").strip()
    mode = req.get("mode", "custom")
    use_ace_sample = False
    if mode == "simple":
        desc = (req.get("description") or "").strip()
        if not desc:
            raise ValueError("Describe the song you want")
        job.update(0.02, "Writing the song")
        written = writing.write_song(desc, instrumental, req.get("language_name") or "English", style)
        if written:
            style = written["style"] or style
            lyrics = written["lyrics"]
            title = title or written["title"]
        elif engine == "acestep":
            use_ace_sample = True
        else:
            lyrics = "[Instrumental]" if instrumental else writing.offline_lyrics(desc)
            style = style or writing.random_style()
            title = title or writing._offline_title(desc)
    if not use_ace_sample and not style and not lyrics:
        raise ValueError("Add lyrics or a style of music")
    if instrumental:
        lyrics = "[Instrumental]"
    duration = req.get("duration")
    duration = min(MAX_DURATION, max(10, float(duration))) if duration not in (None, "", "auto", 0) else None
    reference = _resolve_upload(req.get("voice_upload_id"))
    if not reference and persona and persona.get("reference_path") and Path(persona["reference_path"]).exists():
        reference = Path(persona["reference_path"])
    caption = _caption(style, vocal_gender, instrumental)
    params = {k: req.get(k) for k in ("mode", "description", "instrumental", "vocal_gender", "weirdness",
                                      "style_influence", "negative", "duration", "model", "bpm", "key",
                                      "time_signature", "language", "seed")}
    params["voice_reference"] = bool(reference)
    title = title or (writing._offline_title(req.get("description") or style) if engine == "mock" else "")

    results = []
    if engine == "mock":
        n = int(req.get("batch_size") or s.get("batch_size", 2))
        secs = duration or 30.0
        for i in range(n):
            job.update(0.1 + 0.8 * i / n, f"Rendering demo version {i + 1}/{n}")
            out = TMP_DIR / f"{job.id}_{i}.wav"
            metas = mock.render(out, caption, secs, req.get("bpm"), req.get("key"), instrumental, req.get("seed") or job.id, i)
            mp3 = out.with_suffix(".mp3")
            audio.convert(out, mp3)
            out.unlink()
            results.append((mp3, {"metas": metas, "prompt": caption, "lyrics": lyrics}))
    else:
        p = _ace_common(s, req)
        p.update(_knobs(req.get("weirdness"), req.get("style_influence")))
        p.update({
            "prompt": caption, "lyrics": lyrics, "audio_duration": duration,
            "bpm": int(req["bpm"]) if req.get("bpm") else None, "key_scale": req.get("key") or "",
            "time_signature": req.get("time_signature") or "",
            "lm_negative_prompt": (req.get("negative") or "").strip() or "NO USER INPUT",
        })
        if use_ace_sample:
            desc = req.get("description", "")
            if instrumental and "instrumental" not in desc.lower():
                desc += ", instrumental"
            if vocal_gender in ("male", "female"):
                desc += f", {vocal_gender} vocals"
            p.update({"sample_query": desc, "thinking": True, "prompt": "", "lyrics": ""})
        files = {"reference_audio": str(reference)} if reference else None
        if reference:
            p["audio_cover_strength"] = 1.0
        results = acestep.run_task(job, p, files, TMP_DIR)
    titles = _version_titles(title or "Untitled", len(results))
    for (path, item), t in zip(results, titles):
        final_lyrics = item.get("lyrics") or lyrics
        final_style = style or item.get("prompt") or caption
        if not title and final_lyrics and final_lyrics != "[Instrumental]":
            t = t.replace("Untitled", _title_from_lyrics(final_lyrics))
        tr = _save_track(path, title=t, kind="song", style=final_style, lyrics=final_lyrics, params=params,
                         metas=item.get("metas") or {}, persona_id=(persona or {}).get("id"),
                         album_id=req.get("album_id"), engine=engine)
        job.track_ids.append(tr["id"])
    return {"track_ids": job.track_ids}


def _title_from_lyrics(lyrics):
    lines = [ln.strip() for ln in lyrics.splitlines() if ln.strip() and not ln.strip().startswith("[")]
    counts = {}
    for ln in lines:
        counts[ln] = counts.get(ln, 0) + 1
    hook = max(counts, key=counts.get) if counts else "Untitled"
    words = re.sub(r"[^\w\s']", "", hook).split()
    return " ".join(words[:4]).title() or "Untitled"


# ---------------------------------------------------------------- remix


REMIX_LABELS = {
    "cover": "Cover", "refine": "Smart Refine", "repaint": "Repaint", "extend": "Extended",
    "add_vocals": "+ Vocals", "add_instrumental": "+ Instrumental",
}


def remix(job, track, req):
    s = load_settings()
    engine = s.get("music_engine", "acestep")
    op = req.get("op")
    if op not in REMIX_LABELS:
        raise ValueError(f"Unknown operation {op}")
    src = Path(track["audio_path"])
    dur = track.get("duration") or audio.duration(src)
    style = (req.get("style") or track.get("style") or "").strip()
    lyrics = req.get("lyrics") if req.get("lyrics") is not None else track.get("lyrics", "")
    start = float(req.get("start") or 0)
    end = float(req["end"]) if req.get("end") not in (None, "") else dur
    params = {"op": op, **{k: v for k, v in req.items() if k != "op"}}

    if op == "refine":
        instruction = (req.get("instruction") or "").strip()
        if not instruction:
            raise ValueError("Describe what to change")
        job.update(0.03, "Planning the refinement")
        style, lyrics = _plan_refine(instruction, style, lyrics)
    src_for_task = src
    if op == "add_instrumental" and (start > 0 or end < dur - 0.05):
        src_for_task = TMP_DIR / f"{job.id}_section{src.suffix}"
        audio.trim(src, src_for_task, start, end)

    results = []
    if engine == "mock":
        job.update(0.2, "Rendering demo remix")
        layer = TMP_DIR / f"{job.id}_layer.wav"
        secs = float(req.get("extra") or 30) if op == "extend" else min(dur, 120) or 30
        mock.render(layer, style + (" " + op), secs, None, "", op != "add_vocals", job.id, 1)
        out = TMP_DIR / f"{job.id}_0.mp3"
        if op == "extend":
            audio.run(["-i", str(src), "-i", str(layer), "-filter_complex",
                       "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a];[1:a]aformat=sample_rates=44100:channel_layouts=stereo[b];[a][b]acrossfade=d=1.5[o]",
                       "-map", "[o]", str(out)])
        elif op in ("add_vocals", "add_instrumental"):
            audio.run(["-i", str(src_for_task), "-i", str(layer), "-filter_complex",
                       "[0:a][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[o]", "-map", "[o]", str(out)])
        else:
            audio.convert(layer, out)
        layer.unlink(missing_ok=True)
        results = [(out, {})]
    else:
        p = _ace_common(s, req)
        p.update({"prompt": _caption(style, req.get("vocal_gender", "auto")), "lyrics": lyrics or "", "batch_size": int(req.get("batch_size") or 1)})
        if op == "cover":
            keep = float(req.get("strength", 0.5))
            p.update({"task_type": "cover", "audio_cover_strength": max(0.0, min(1.0, keep))})
        elif op in ("repaint", "refine") and (start > 0 or end < dur - 0.05):
            p.update({"task_type": "repaint", "repainting_start": start, "repainting_end": end, "chunk_mask_mode": "explicit"})
        elif op == "refine":
            p.update({"task_type": "cover", "audio_cover_strength": float(req.get("strength", 0.6))})
        elif op == "repaint":
            p.update({"task_type": "repaint", "repainting_start": 0.0, "repainting_end": -1})
        elif op == "extend":
            extra = max(5.0, min(240.0, float(req.get("extra") or 30)))
            p.update({"task_type": "repaint", "repainting_start": dur, "repainting_end": dur + extra,
                      "chunk_mask_mode": "explicit", "audio_duration": dur + extra})
        elif op == "add_vocals":
            if not (lyrics or "").strip() or lyrics.strip() == "[Instrumental]":
                raise ValueError("Enter the lyrics to sing")
            p.update({"task_type": "lego", "track_name": "vocals", "global_caption": track.get("style", ""),
                      "repainting_start": start, "repainting_end": end, "model": s.get("acestep_base_model"),
                      "inference_steps": max(32, p["inference_steps"]), "thinking": True})
        elif op == "add_instrumental":
            classes = req.get("instruments") or ["drums", "bass", "guitar", "keyboard", "strings"]
            p.update({"task_type": "complete", "track_classes": classes, "lyrics": lyrics or "",
                      "model": s.get("acestep_base_model"), "inference_steps": max(32, p["inference_steps"]),
                      "thinking": True})
        results = acestep.run_task(job, p, {"src_audio": str(src_for_task)}, TMP_DIR)
    if src_for_task != src:
        Path(src_for_task).unlink(missing_ok=True)
    label = REMIX_LABELS[op]
    titles = _version_titles(f"{track['title']} [{label}]", len(results))
    for (path, item), t in zip(results, titles):
        tr = _save_track(path, title=t, kind=op, style=style, lyrics=lyrics if op != "add_instrumental" else track.get("lyrics", ""),
                         params=params, metas=item.get("metas") or {}, parent_id=track["id"],
                         album_id=track.get("album_id"), persona_id=track.get("persona_id"), engine=engine)
        job.track_ids.append(tr["id"])
    return {"track_ids": job.track_ids}


def _plan_refine(instruction, style, lyrics):
    try:
        d = llm.chat_json(
            writing.SYSTEM_SONG,
            f"Current style: {style}\nCurrent lyrics:\n{lyrics}\n\nThe user wants this change: {instruction}\n"
            'Return {"style": new comma-separated style, "lyrics": full updated lyrics (unchanged if the request is only about sound)}.',
            temperature=0.7,
        )
        return d.get("style") or style, d.get("lyrics") or lyrics
    except (llm.LLMUnavailable, ValueError):
        return ", ".join(x for x in (style, instruction) if x), lyrics


# ---------------------------------------------------------------- local edits


def fade(job, track, req):
    src = Path(track["audio_path"])
    fi = float(req.get("fade_in") or 0)
    fo = float(req.get("fade_out") or 0)
    fos = req.get("fade_out_start")
    fos = float(fos) if fos not in (None, "") else None
    if fi <= 0 and fo <= 0:
        raise ValueError("Choose a fade-in and/or fade-out duration")
    out = TMP_DIR / f"{job.id}{src.suffix}"
    audio.fade(src, out, fi, fos, fo)
    label = " / ".join(x for x in ("Fade in" if fi else "", "Fade out" if fo else "") if x)
    tr = _save_track(out, title=f"{track['title']} [{label}]", kind="fade", style=track["style"], lyrics=track["lyrics"],
                     params=req, metas=track.get("metas") or {}, parent_id=track["id"], album_id=track.get("album_id"),
                     engine="ffmpeg")
    job.track_ids.append(tr["id"])
    return {"track_ids": job.track_ids}


def separate(job, track, req):
    if not stems.available():
        raise RuntimeError("Demucs is not installed. Run Install again from Pinokio (or `pip install demucs`).")
    out_dir = TMP_DIR / f"stems_{job.id}"
    res = stems.separate(track["audio_path"], out_dir, job, two_stems=req.get("mode", "two") == "two")
    job.update(0.9, "Saving stems")
    for name, path in res.items():
        mp3 = path.with_suffix(".mp3")
        audio.convert(path, mp3)
        tr = _save_track(mp3, title=f"{track['title']} [{name.replace('_', ' ').title()}]", kind="stem",
                         style=track["style"], lyrics=track["lyrics"] if name == "vocals" else "",
                         params={"stem": name}, parent_id=track["id"], album_id=track.get("album_id"), engine="demucs")
        job.track_ids.append(tr["id"])
    shutil.rmtree(out_dir, ignore_errors=True)
    return {"track_ids": job.track_ids}


def render_video(job, track, req):
    job.update(0.1, "Rendering music video")
    dst = EXPORT_DIR / f"{track['id']}.mp4"
    sub = track.get("style", "")[:80]
    audio.make_video(track["audio_path"], track["cover_path"], dst, track["title"], sub,
                     track.get("lyrics", "") if req.get("lyrics", True) else "")
    store.update("tracks", track["id"], {"video_path": str(dst)})
    job.track_ids.append(track["id"])
    return {"video": f"/api/tracks/{track['id']}/download?format=mp4"}


def export(track, fmt):
    src = Path(track["audio_path"])
    if fmt == "mp4":
        p = Path(track.get("video_path") or "")
        if not p.exists():
            raise FileNotFoundError("Render the music video first")
        return p
    if src.suffix.lstrip(".") == fmt:
        return src
    dst = EXPORT_DIR / f"{track['id']}.{fmt}"
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        audio.convert(src, dst, fmt)
    return dst


def import_upload(path, title, kind="upload"):
    path = Path(path)
    tmp = TMP_DIR / f"imp_{store.new_id()}{path.suffix.lower()}"
    shutil.copy(path, tmp)
    return _save_track(tmp, title=title or path.stem, kind=kind, engine="upload")


# ---------------------------------------------------------------- speech


def _tone_speed(tone, base):
    t = (tone or "").lower()
    if any(w in t for w in ("slow", "calm", "sooth", "whisper", "gentle", "relax", "sleep")):
        base *= 0.92
    if any(w in t for w in ("energetic", "excited", "fast", "upbeat", "hype")):
        base *= 1.08
    return round(max(0.6, min(1.4, base)), 3)


def _alt_voice(voice):
    v = next((x for x in tts.VOICES if x["id"] == voice), tts.VOICES[0])
    same = [x["id"] for x in tts.VOICES if x["lang"] == v["lang"] and x["id"] != voice and x["id"][1] == voice[1]]
    return random.choice(same) if same else voice


def speech(job, req):
    if not tts.available():
        raise RuntimeError("Kokoro TTS is not installed. Run Install again from Pinokio (or `pip install kokoro`).")
    preset = req.get("preset") or "voiceover"
    pre = writing.SPEECH_PRESETS.get(preset, writing.SPEECH_PRESETS["voiceover"])
    if req.get("mode") == "simple":
        desc = (req.get("description") or "").strip()
        if not desc:
            raise ValueError("Describe what the speech should say")
        job.update(0.03, "Writing the script")
        plan = writing.speech_script(desc, preset, req.get("length", "short"))
        script, tone, music_style, title = plan["script"], plan["tone"], plan["music_style"], plan["title"]
    else:
        script = (req.get("script") or "").strip()
        if not script:
            raise ValueError("Enter the script to read")
        tone = req.get("tone") or pre["tone"]
        music_style = req.get("music_style") or pre["music"]
        title = req.get("title") or writing._offline_title(script)
    voice = req.get("voice") or pre["voice"]
    variety = max(0, min(100, int(req.get("variety", 40))))
    base_speed = float(req.get("speed") or pre["speed"])
    takes = [(voice, _tone_speed(tone, base_speed))]
    if int(req.get("versions", 2)) > 1:
        alt = _alt_voice(voice) if variety >= 50 else voice
        jitter = 1 + (random.uniform(-1, 1) * variety / 100 * 0.12)
        takes.append((alt, round(_tone_speed(tone, base_speed) * jitter, 3)))
    background = bool(req.get("background", True))
    bed = None
    if background:
        job.update(0.1, "Composing background music")
        bed = _make_bed(job, music_style, script)
    for i, (v, sp) in enumerate(takes):
        job.update(0.5 + 0.4 * i / len(takes), f"Recording take {i + 1}/{len(takes)} ({v})")
        wav = TMP_DIR / f"{job.id}_voice{i}.wav"
        tts.synthesize(script, wav, voice=v, speed=sp)
        out = TMP_DIR / f"{job.id}_speech{i}.mp3"
        if bed:
            audio.mix_voice_over(wav, bed, out, bed_volume=float(req.get("music_volume", 0.35)))
        else:
            audio.convert(wav, out)
        wav.unlink(missing_ok=True)
        tr = _save_track(out, title=title if len(takes) == 1 else f"{title} (take {i + 1})", kind="speech",
                         style=f"{tone}" + (f" | {music_style}" if bed else ""), lyrics=script,
                         params={"preset": preset, "voice": v, "speed": sp, "background": background, "tone": tone,
                                 "music_style": music_style if bed else ""},
                         album_id=req.get("album_id"), engine="kokoro")
        job.track_ids.append(tr["id"])
    if bed:
        Path(bed).unlink(missing_ok=True)
    return {"track_ids": job.track_ids}


def _make_bed(job, music_style, script):
    words = len(script.split())
    secs = min(MAX_DURATION, max(20.0, words / 2.4 + 6))
    caption = _caption(music_style, instrumental=True, extra="background music, soft, unobtrusive")
    if engine_name() == "mock":
        out = TMP_DIR / f"{job.id}_bed.wav"
        mock.render(out, caption, secs, None, "", True, job.id, 0)
        return out
    s = load_settings()
    p = _ace_common(s, {})
    p.update({"prompt": caption, "lyrics": "[Instrumental]", "audio_duration": secs, "batch_size": 1, "thinking": False})
    res = acestep.run_task(_Sub(job, 0.1, 0.45), p, None, TMP_DIR)
    return res[0][0]


class _Sub:
    """Maps a sub-task's 0..1 progress into a slice of the parent job."""

    def __init__(self, job, a, b):
        self.job, self.a, self.b, self.id = job, a, b, job.id + "b"

    def update(self, progress=None, message=None):
        self.job.update(None if progress is None else self.a + (self.b - self.a) * progress, message)


def make_persona(job, req):
    """Build a persona from an uploaded/recorded clip or a library track, optionally trimmed and vocal-isolated."""
    track = store.get("tracks", req["track_id"]) if req.get("track_id") else None
    src = _resolve_upload(req.get("voice_upload_id")) if req.get("voice_upload_id") else None
    if not src and track:
        src = Path(track["audio_path"])
    pid = store.new_id()
    ref = ""
    if src:
        if not src.exists():
            raise ValueError("Voice audio not found")
        dur = audio.duration(src)
        start = max(0.0, float(req.get("start") or 0))
        end = float(req["end"]) if req.get("end") not in (None, "") else dur
        end = min(dur, end) if dur else end
        if end - start < 3:
            raise ValueError("Use at least 3 seconds of audio for the voice reference")
        job.update(0.05, "Preparing voice clip")
        clip = TMP_DIR / f"{job.id}_clip.wav"
        if start > 0 or (dur and end < dur - 0.05):
            audio.trim(src, clip, start, end)
        else:
            audio.to_wav(src, clip)
        if req.get("isolate_vocals"):
            if not stems.available():
                raise RuntimeError("Demucs is not installed, so vocals can't be isolated. Untick the option or install demucs.")
            res = stems.separate(clip, TMP_DIR / f"persona_{job.id}", job, two_stems=True)
            shutil.move(str(res["vocals"]), clip)
            shutil.rmtree(TMP_DIR / f"persona_{job.id}", ignore_errors=True)
        dst = PERSONA_DIR / f"{pid}.wav"
        shutil.move(str(clip), dst)
        ref = str(dst)
    elif not (req.get("style") or "").strip():
        raise ValueError("Give the persona a voice clip or a vocal style")
    job.update(0.95, "Saving persona")
    p = store.insert("personas", {
        "id": pid, "name": (req.get("name") or "").strip() or (track or {}).get("title") or "Persona",
        "style": req.get("style") if req.get("style") is not None else (track or {}).get("style", ""),
        "vocal_gender": req.get("vocal_gender") or "auto", "reference_path": ref,
        "source_track_id": (track or {}).get("id"), "notes": req.get("notes", ""),
    })
    return {"persona_id": p["id"]}


def status():
    s = load_settings()
    ace_up = acestep.health() if s.get("music_engine") == "acestep" else False
    return {
        "music_engine": s.get("music_engine"),
        "acestep": {"url": s.get("acestep_url"), "online": ace_up, "models": acestep.models() if ace_up else {}},
        "llm": llm.status(),
        "tts": tts.available(),
        "demucs": stems.available(),
        "ffmpeg": audio.have_ffmpeg(),
    }
