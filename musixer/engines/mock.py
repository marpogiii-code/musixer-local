"""Procedural demo engine so the whole app can be exercised without a GPU or model download.

It does not sing or follow lyrics; it renders a short synth groove whose tempo, key and
mood follow the request, so every workflow (library, remix, stems, video, speech beds) works.
"""
import hashlib
import re
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
PROGS = [[0, 5, 3, 4], [0, 4, 5, 3], [5, 3, 0, 4], [0, 3, 4, 4]]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]


def _seed(*parts):
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _bpm(style, bpm):
    if bpm:
        return int(bpm)
    m = re.search(r"(\d{2,3})\s*bpm", style or "", re.I)
    if m:
        return int(m.group(1))
    s = (style or "").lower()
    if any(w in s for w in ("ambient", "ballad", "meditation", "lofi", "lo-fi", "sleep", "calm")):
        return 76
    if any(w in s for w in ("drum and bass", "dnb", "techno", "edm", "punk", "metal")):
        return 140
    return 112


def _env(n, attack=0.01, release=0.2):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((n / SR - t) / max(release, 1e-4), 0, 1)
    return a * r


def render(path, style="", seconds=30.0, bpm=None, key="", instrumental=True, seed=0, variant=0):
    rng = np.random.default_rng(_seed(style, seed, variant))
    bpm = _bpm(style, bpm)
    minor = "minor" in (key or "").lower() or bool(re.search(r"\b(sad|dark|melanchol|minor)", style or "", re.I))
    root_name = (key or "").split(" ")[0].strip().upper()[:2].rstrip("M") or "CDEFGAB"[rng.integers(0, 7)]
    root = 48 + NOTES.get(root_name, 0)
    scale = MINOR if minor else MAJOR
    prog = PROGS[rng.integers(0, len(PROGS))]
    n = int(seconds * SR)
    out = np.zeros((2, n), dtype=np.float32)
    beat = 60.0 / bpm
    bar = beat * 4

    def note_hz(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    t_all = np.arange(n) / SR
    for b in range(int(seconds / bar) + 1):
        start = int(b * bar * SR)
        if start >= n:
            break
        deg = prog[b % len(prog)]
        chord = [root + scale[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4)]
        seg = min(int(bar * SR), n - start)
        t = t_all[:seg]
        pad = sum(np.sin(2 * np.pi * note_hz(m + 12) * t) for m in chord) / 3
        pad *= _env(seg, 0.3, 0.4) * 0.16
        bass_f = note_hz(chord[0] - 12)
        bass = np.sign(np.sin(2 * np.pi * bass_f * t)) * 0.06 * _env(seg, 0.01, 0.1)
        out[0, start:start + seg] += pad + bass
        out[1, start:start + seg] += pad * 0.9 + bass
        for s in range(8):
            ns = start + int(s * beat / 2 * SR)
            ln = int(beat / 2 * SR)
            if ns + ln > n:
                break
            m = chord[rng.integers(0, 3)] + 24 + (12 if rng.random() < 0.2 else 0)
            tt = t_all[:ln]
            lead = np.sin(2 * np.pi * note_hz(m) * tt) * np.exp(-tt * 6) * (0.10 if not instrumental else 0.07)
            pan = 0.5 + 0.4 * np.sin(s)
            out[0, ns:ns + ln] += lead * (1 - pan)
            out[1, ns:ns + ln] += lead * pan
    for k in range(int(seconds / beat) + 1):
        ks = int(k * beat * SR)
        ln = int(0.25 * SR)
        if ks + ln > n:
            break
        tt = t_all[:ln]
        kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12) * 0.35
        out[:, ks:ks + ln] += kick
        if k % 2 == 1:
            snare = rng.standard_normal(ln) * np.exp(-tt * 22) * 0.12
            out[:, ks:ks + ln] += snare
        hs = ks + int(beat / 2 * SR)
        hl = int(0.05 * SR)
        if hs + hl < n:
            out[:, hs:hs + hl] += rng.standard_normal(hl) * np.exp(-t_all[:hl] * 80) * 0.05
    fade = int(min(2.0, seconds / 6) * SR)
    out[:, :fade] *= np.linspace(0, 1, fade)
    out[:, -fade:] *= np.linspace(1, 0, fade)
    peak = np.abs(out).max() or 1.0
    out = out / peak * 0.85
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), out.T, SR)
    return {"bpm": bpm, "keyscale": f"{root_name} {'minor' if minor else 'major'}", "duration": seconds}
