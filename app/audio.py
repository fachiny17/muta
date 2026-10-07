"""Audio normalisation: any input -> 16 kHz mono 16-bit WAV, split into <=28 s chunks.

Uses FFmpeg for decoding and the standard library for chunking (no pydub, so it
works on any Python version).
"""
import array
import math
import os
import shutil
import subprocess
import sys
import uuid
import wave

SR = 16000


class AudioError(Exception):
    pass


def _ffmpeg():
    """System ffmpeg if present, otherwise the static binary bundled by imageio-ffmpeg (works on Render)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def to_wav(src: str, workdir: str) -> str:
    dst = os.path.join(workdir, f"{uuid.uuid4().hex}.wav")
    exe = _ffmpeg()
    if not exe:
        raise AudioError("ffmpeg is not available on the server")
    try:
        subprocess.run([exe, "-y", "-i", src, "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", dst],
                       check=True, capture_output=True, timeout=60)
    except FileNotFoundError:
        raise AudioError("ffmpeg is not installed on the server")
    except subprocess.CalledProcessError:
        raise AudioError("could not decode the audio file")
    except subprocess.TimeoutExpired:
        raise AudioError("audio conversion timed out")
    return dst


def _read(path: str) -> array.array:
    with wave.open(path, "rb") as w:
        if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise AudioError("wav must be 16 kHz mono 16-bit")
        samples = array.array("h")
        samples.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def duration_s(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _write(path: str, samples: array.array) -> None:
    if sys.byteorder == "big":
        samples = array.array("h", samples); samples.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(samples.tobytes())


def chunk_wav(path: str, workdir: str, max_s: int = 28, search_s: int = 6) -> list:
    """Split long audio at the quietest 100 ms moment near each max_s boundary."""
    samples = _read(path)
    limit = max_s * SR
    if len(samples) <= limit:
        return [path]
    frame = SR // 10
    cuts, start = [], 0
    while len(samples) - start > limit:
        end = start + limit
        lo = max(start + (max_s - search_s) * SR, start + SR)
        best, best_rms = end, float("inf")
        for pos in range(lo, end - frame, frame):
            seg = samples[pos:pos + frame]
            rms = math.sqrt(sum(x * x for x in seg) / len(seg))
            if rms < best_rms:
                best, best_rms = pos + frame // 2, rms
        cuts.append((start, best))
        start = best
    cuts.append((start, len(samples)))
    out = []
    for a, b in cuts:
        p = os.path.join(workdir, f"{uuid.uuid4().hex}.wav")
        _write(p, samples[a:b]); out.append(p)
    return out
