"""ffmpeg/numpy helpers for conversion, fades, mixing, waveforms, video and cover art."""
import colorsys
import hashlib
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

FORMATS = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
    "m4a": ["-c:a", "aac", "-b:a", "256k"],
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
}


def run(args):
    p = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr.strip()[-800:]}")


def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


def duration(path):
    p = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(json.loads(p.stdout)["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        return 0.0


def convert(src, dst, fmt=None):
    fmt = fmt or Path(dst).suffix.lstrip(".")
    run(["-i", str(src), "-vn", *FORMATS.get(fmt, []), str(dst)])
    return Path(dst)


def to_wav(src, dst, sr=48000, channels=2):
    run(["-i", str(src), "-vn", "-ac", str(channels), "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)])
    return Path(dst)


def decode(src, sr=44100, channels=2):
    p = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(src), "-f", "f32le", "-ac", str(channels), "-ar", str(sr), "-"],
        capture_output=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="ignore")[-500:])
    data = np.frombuffer(p.stdout, dtype=np.float32)
    return data.reshape(-1, channels).T.copy()


def fade(src, dst, fade_in=0.0, fade_out_start=None, fade_out=0.0):
    filters = []
    if fade_in and fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out and fade_out > 0:
        total = duration(src)
        start = fade_out_start if fade_out_start is not None else max(0.0, total - fade_out)
        filters.append(f"afade=t=out:st={start:.3f}:d={fade_out:.3f}")
    args = ["-i", str(src)]
    if filters:
        args += ["-af", ",".join(filters)]
    run([*args, *FORMATS.get(Path(dst).suffix.lstrip("."), []), str(dst)])
    return Path(dst)


def trim(src, dst, start, end):
    run(["-i", str(src), "-ss", f"{start:.3f}", "-to", f"{end:.3f}", str(dst)])
    return Path(dst)


def mix_voice_over(voice, bed, dst, bed_volume=0.35, lead_in=1.5, tail=2.0):
    """Lay a voice over a music bed with sidechain ducking, a short intro and a faded tail."""
    vdur = duration(voice)
    total = vdur + lead_in + tail
    delay = int(lead_in * 1000)
    graph = (
        f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,adelay={delay}|{delay},apad=whole_dur={total:.2f},asplit=2[v1][v2];"
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,atrim=0:{total:.2f},"
        f"volume={bed_volume:.2f},afade=t=out:st={max(0.0, total - tail - 0.5):.2f}:d={tail + 0.5:.2f}[b];"
        f"[b][v1]sidechaincompress=threshold=0.04:ratio=6:attack=20:release=400[d];"
        f"[d][v2]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[out]"
    )
    run(["-i", str(voice), "-stream_loop", "-1", "-i", str(bed), "-filter_complex", graph, "-map", "[out]",
         *FORMATS.get(Path(dst).suffix.lstrip("."), []), str(dst)])
    return Path(dst)


def peaks(path, count=160):
    try:
        data = decode(path, sr=8000, channels=1)[0]
    except RuntimeError:
        return []
    if data.size == 0:
        return []
    chunks = np.array_split(np.abs(data), count)
    vals = np.array([c.max() if c.size else 0.0 for c in chunks])
    top = vals.max() or 1.0
    return [round(float(v / top), 3) for v in vals]


def _palette(seed_text):
    h = hashlib.sha256(seed_text.encode()).digest()
    base = h[0] / 255.0
    cols = []
    for i in range(3):
        hue = (base + i * (0.12 + h[i + 1] / 2550.0)) % 1.0
        r, g, b = colorsys.hls_to_rgb(hue, 0.45 + (h[i + 4] / 255.0) * 0.2, 0.65 + (h[i + 7] / 255.0) * 0.3)
        cols.append((int(r * 255), int(g * 255), int(b * 255)))
    return cols, h


def _font(size):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "Helvetica.ttc"):
        for root in ("/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "C:/Windows/Fonts", "/System/Library/Fonts"):
            p = Path(root) / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except OSError:
                    pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def make_cover(dst, title, style="", size=768):
    """Procedural gradient cover art seeded by title and style."""
    cols, h = _palette(f"{title}|{style}")
    img = Image.new("RGB", (size, size), cols[0])
    draw = ImageDraw.Draw(img)
    for i in range(7):
        r = int(size * (0.25 + h[10 + i] / 255.0 * 0.5))
        x = int(h[17 + i] / 255.0 * size)
        y = int(h[24 + i] / 255.0 * size)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=cols[(i % 2) + 1])
    img = img.filter(ImageFilter.GaussianBlur(size // 10))
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(0, size, 6):
        a = int(40 + 30 * np.sin(i / 37.0 + h[3]))
        od.line([(0, i), (size, i)], fill=(255, 255, 255, max(0, a // 6)))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, quality=92)
    return Path(dst)


def make_video(audio, cover, dst, title="", subtitle="", lyrics="", width=1280, height=720):
    """Render an MP4 music video: blurred cover background, artwork, title, lyrics and live waveform."""
    frame = Path(dst).with_suffix(".frame.png")
    bg = Image.open(cover).convert("RGB").resize((width, width)).crop((0, (width - height) // 2, width, (width + height) // 2))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    dark = Image.new("RGB", bg.size, (0, 0, 0))
    bg = Image.blend(bg, dark, 0.45)
    art_size = int(height * 0.58)
    art = Image.open(cover).convert("RGB").resize((art_size, art_size))
    bg.paste(art, (80, 70))
    d = ImageDraw.Draw(bg)
    tx = 80 + art_size + 60
    d.text((tx, 90), textwrap.shorten(title or "Untitled", 40), font=_font(48), fill=(255, 255, 255))
    if subtitle:
        d.text((tx, 160), textwrap.shorten(subtitle, 70), font=_font(22), fill=(220, 220, 230))
    if lyrics:
        lines = [ln for ln in lyrics.splitlines() if ln.strip() and not ln.strip().startswith("[")][:10]
        y = 220
        for ln in lines:
            d.text((tx, y), textwrap.shorten(ln, 48), font=_font(22), fill=(235, 235, 245))
            y += 32
    bg.save(frame)
    wh = 140
    graph = (
        f"[1:a]showwaves=s={width}x{wh}:mode=cline:rate=25:colors=0xffffff@0.85,format=rgba[w];"
        f"[0:v][w]overlay=0:{height - wh - 20}:format=auto,format=yuv420p[v]"
    )
    try:
        run(["-loop", "1", "-framerate", "25", "-i", str(frame), "-i", str(audio), "-filter_complex", graph,
             "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
             "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", str(dst)])
    finally:
        frame.unlink(missing_ok=True)
    return Path(dst)
