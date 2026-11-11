# Musixer Local

A local, login-free AI music studio inspired by aimusixer.me. Every "Pro" workflow runs on your own machine with open models: no account, no credits, no limits.

This is an independent app. It does not use aimusixer.me's servers or bypass its paywall; it reimplements the same jobs with open-source models.

| Feature | How it runs locally |
| --- | --- |
| Create (Simple / Custom), instrumental, vocal gender, weirdness, style influence, exclude styles, up to 10 min, versions, seed, BPM / key / time signature | [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) `text2music` |
| Upload Voice / Personas (reusable voice + style; voice from an uploaded file, a mic recording or a library track, with trimming and optional Demucs vocal isolation) | ACE-Step reference audio |
| Cover (new style, same song) | ACE-Step `cover` |
| Smart Refine (plain-language change, optional section) | LLM rewrites style/lyrics, then ACE-Step `cover` / `repaint` |
| Repaint a section, Extend | ACE-Step `repaint` |
| Add Vocals / Add Instrumental | ACE-Step base model `lego` / `complete` |
| Vocal separation (2 or 4 stems) | Demucs `htdemucs` |
| Fade in / out, MP3 / M4A / WAV / FLAC export | ffmpeg |
| MP4 music video (cover, title, waveform, lyrics) | ffmpeg |
| Library, albums, favorites, uploads, custom cover art | SQLite + files in `data/` |
| Lyrics generator, AI Lyric Studio (13 co-writer actions, drafts, version history), style generator, enhance / random style | Ollama or any OpenAI-compatible API, with offline templates as fallback |
| AI Speech (Simple / Advanced, tone, voices, speed, variety, voice-over / ASMR / bedtime story / meditation / podcast presets, background music with ducking) | Kokoro-82M TTS + ACE-Step instrumental bed |

Not included: Google Lyria (closed model) and lip-synced singer videos.

## Install

### Pinokio (one click)
Add this folder to Pinokio, then click **Install** and **Start**. ACE-Step downloads its models (about 10 GB) on first start. **Start (demo synth, no GPU)** runs the whole app with a procedural synth instead of ACE-Step, which is handy for trying the UI.

### Manual
Needs Python 3.10+, ffmpeg, espeak-ng, and [uv](https://docs.astral.sh/uv/).

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # add the right torch build for your GPU first
git clone https://github.com/ace-step/ACE-Step-1.5 app/ACE-Step-1.5 && (cd app/ACE-Step-1.5 && uv sync)
./start.sh            # ACE-Step API on :8001 + Musixer on http://127.0.0.1:7870
./start.sh --mock     # demo synth only, no GPU or model download needed
```

If ACE-Step already runs elsewhere, set its URL in **Settings**.

## Hardware
ACE-Step 1.5 turbo needs about 4 GB of VRAM (NVIDIA CUDA, AMD ROCm, or Apple Silicon). CPU works but is slow. Kokoro, Demucs and the writing tools run fine on CPU.

## Configuration
Settings are saved in `data/settings.json` and can be changed in the UI. Environment overrides: `MUSIXER_PORT` (7870), `MUSIXER_HOST`, `MUSIXER_DATA`, `MUSIXER_MUSIC_ENGINE` (`acestep` or `mock`), `ACESTEP_URL`, `ACESTEP_API_KEY`, `OLLAMA_HOST`, `MUSIXER_OLLAMA_MODEL`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MUSIXER_OPENAI_MODEL`.

## Layout
```
musixer/
  main.py        FastAPI routes
  services.py    song / remix / stems / fade / video / speech workflows
  writing.py     lyrics, styles, lyric studio, speech scripts (LLM + offline)
  engines/       acestep.py (API client), mock.py, llm.py, tts.py (Kokoro), stems.py (Demucs)
  audio.py       ffmpeg helpers, waveform, cover art, video
  store.py jobs.py config.py
web/             single-page UI (no build step)
*.js             Pinokio launcher scripts
```
