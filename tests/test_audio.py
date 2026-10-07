import wave
from app import audio
from tests.conftest import make_wav


def test_chunk_splits_in_quiet_gap(tmp_path):
    clip = make_wav(tmp_path / "a.wav", 40, gaps=[(25, 25.5)])
    parts = audio.chunk_wav(clip, str(tmp_path))
    assert len(parts) == 2
    first = audio.duration_s(parts[0])
    assert 24.9 < first < 25.7  # cut landed in the silent gap, not at the 28 s limit
    assert all(audio.duration_s(p) <= 28.01 for p in parts)


def test_short_audio_not_split(tmp_path):
    clip = make_wav(tmp_path / "b.wav", 5)
    assert audio.chunk_wav(clip, str(tmp_path)) == [clip]
