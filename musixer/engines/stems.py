"""Vocal / stem separation with Demucs (htdemucs). Audio IO goes through ffmpeg + soundfile."""
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import audio

_model = None
_lock = threading.Lock()


def available():
    try:
        import demucs  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def separate(src, out_dir, job=None, two_stems=True):
    """Returns dict stem_name -> wav path. two_stems=True gives vocals + instrumental."""
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    global _model
    with _lock:
        if _model is None:
            if job:
                job.update(0.05, "Loading Demucs model")
            _model = get_model("htdemucs")
            _model.eval()
    model = _model
    device = "cuda" if torch.cuda.is_available() else ("mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu")
    wav = torch.from_numpy(audio.decode(src, sr=model.samplerate, channels=model.audio_channels))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    if job:
        job.update(0.15, f"Separating stems on {device}")
    with torch.no_grad():
        sources = apply_model(model.to(device), ((wav - mean) / std)[None].to(device), device=device,
                              shifts=1, split=True, overlap=0.25, progress=False)[0]
    sources = (sources * std + mean).cpu().numpy()
    names = list(model.sources)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    if two_stems:
        vi = names.index("vocals")
        stems = {"vocals": sources[vi], "instrumental": np.sum([s for i, s in enumerate(sources) if i != vi], axis=0)}
    else:
        stems = dict(zip(names, sources))
    for name, data in stems.items():
        p = out_dir / f"{name}.wav"
        peak = float(np.abs(data).max() or 1.0)
        sf.write(str(p), (data / max(1.0, peak)).T, model.samplerate)
        result[name] = p
    return result
