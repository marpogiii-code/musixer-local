import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MUSIXER_DATA", ROOT / "data")).resolve()
AUDIO_DIR = DATA_DIR / "audio"
COVER_DIR = DATA_DIR / "covers"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
TMP_DIR = DATA_DIR / "tmp"
PERSONA_DIR = DATA_DIR / "personas"
WEB_DIR = ROOT / "web"
SETTINGS_PATH = DATA_DIR / "settings.json"

for _d in (DATA_DIR, AUDIO_DIR, COVER_DIR, UPLOAD_DIR, EXPORT_DIR, TMP_DIR, PERSONA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULTS = {
    "music_engine": os.environ.get("MUSIXER_MUSIC_ENGINE", "acestep"),
    "acestep_url": os.environ.get("ACESTEP_URL", "http://127.0.0.1:8001"),
    "acestep_api_key": os.environ.get("ACESTEP_API_KEY", ""),
    "acestep_thinking": True,
    "acestep_steps": 8,
    "acestep_base_model": "acestep-v15-base",
    "batch_size": 2,
    "llm_provider": os.environ.get("MUSIXER_LLM_PROVIDER", "auto"),
    "ollama_url": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    "ollama_model": os.environ.get("MUSIXER_OLLAMA_MODEL", ""),
    "openai_base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
    "openai_model": os.environ.get("MUSIXER_OPENAI_MODEL", "gpt-4o-mini"),
    "tts_engine": os.environ.get("MUSIXER_TTS_ENGINE", "kokoro"),
    "default_voice": "af_heart",
}

SECRET_KEYS = {"openai_api_key", "acestep_api_key"}

_lock = threading.Lock()
_cache = None


def load_settings():
    global _cache
    with _lock:
        if _cache is None:
            data = {}
            if SETTINGS_PATH.exists():
                try:
                    data = json.loads(SETTINGS_PATH.read_text())
                except ValueError:
                    data = {}
            _cache = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
        return dict(_cache)


def save_settings(patch):
    global _cache
    current = load_settings()
    for k, v in patch.items():
        if k not in DEFAULTS:
            continue
        if k in SECRET_KEYS and v == "********":
            continue
        current[k] = v
    with _lock:
        SETTINGS_PATH.write_text(json.dumps(current, indent=2))
        _cache = current
    return dict(current)


def public_settings():
    s = load_settings()
    for k in SECRET_KEYS:
        if s.get(k):
            s[k] = "********"
    return s
