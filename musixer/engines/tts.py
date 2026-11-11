"""Local text-to-speech with Kokoro-82M (Apache-2.0)."""
import re
import threading

import numpy as np
import soundfile as sf

SR = 24000
VOICES = [
    {"id": "af_heart", "name": "Heart (US female, warm)", "lang": "a"},
    {"id": "af_bella", "name": "Bella (US female, bright)", "lang": "a"},
    {"id": "af_nicole", "name": "Nicole (US female, soft/ASMR)", "lang": "a"},
    {"id": "af_sarah", "name": "Sarah (US female)", "lang": "a"},
    {"id": "af_sky", "name": "Sky (US female)", "lang": "a"},
    {"id": "am_michael", "name": "Michael (US male)", "lang": "a"},
    {"id": "am_adam", "name": "Adam (US male, deep)", "lang": "a"},
    {"id": "am_fenrir", "name": "Fenrir (US male)", "lang": "a"},
    {"id": "am_puck", "name": "Puck (US male, playful)", "lang": "a"},
    {"id": "bf_emma", "name": "Emma (UK female)", "lang": "b"},
    {"id": "bf_isabella", "name": "Isabella (UK female)", "lang": "b"},
    {"id": "bm_george", "name": "George (UK male, narrator)", "lang": "b"},
    {"id": "bm_lewis", "name": "Lewis (UK male)", "lang": "b"},
    {"id": "ef_dora", "name": "Dora (Spanish female)", "lang": "e"},
    {"id": "em_alex", "name": "Alex (Spanish male)", "lang": "e"},
    {"id": "ff_siwis", "name": "Siwis (French female)", "lang": "f"},
    {"id": "if_sara", "name": "Sara (Italian female)", "lang": "i"},
    {"id": "pf_dora", "name": "Dora (Portuguese female)", "lang": "p"},
    {"id": "jf_alpha", "name": "Alpha (Japanese female)", "lang": "j"},
    {"id": "zf_xiaobei", "name": "Xiaobei (Mandarin female)", "lang": "z"},
    {"id": "hf_alpha", "name": "Alpha (Hindi female)", "lang": "h"},
]
_VOICE_LANG = {v["id"]: v["lang"] for v in VOICES}
_pipes = {}
_lock = threading.Lock()


def available():
    try:
        import kokoro  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _pipe(lang):
    from kokoro import KPipeline

    with _lock:
        if lang not in _pipes:
            _pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        return _pipes[lang]


def clean_script(text):
    text = re.sub(r"\[[^\]]*\]", " ", text or "")
    text = re.sub(r"[*_#>`]", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def synthesize(text, path, voice="af_heart", speed=1.0, pause=0.35):
    lang = _VOICE_LANG.get(voice, voice[0] if voice else "a")
    pipe = _pipe(lang)
    gap = np.zeros(int(SR * pause), dtype=np.float32)
    parts = []
    for para in [p for p in re.split(r"\n\s*\n", clean_script_keep_paras(text)) if p.strip()]:
        for _, _, audio in pipe(para, voice=voice, speed=speed, split_pattern=r"\n+"):
            if audio is None:
                continue
            a = audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio)
            parts.append(a.astype(np.float32))
        parts.append(gap)
    if not parts:
        raise RuntimeError("Nothing to read: the script is empty")
    sf.write(str(path), np.concatenate(parts), SR)
    return path


def clean_script_keep_paras(text):
    return "\n\n".join(clean_script(p) for p in re.split(r"\n\s*\n", text or ""))
