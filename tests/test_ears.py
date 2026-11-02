import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import urllib.error

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from test_dude import _run, dd
from test_life import _quiet

import ears
from ears import SR, Ears, beat_strength, classify, clean_line, vote

rng = np.random.default_rng(7)


def click_track(secs=6.0, bpm=120):
    """Kick-ish clicks on a beat over a soft pad: music."""
    x = 0.05 * np.sin(2 * np.pi * 220 * np.arange(int(secs * SR)) / SR)
    step = int(SR * 60 / bpm)
    for i in range(0, len(x) - 800, step):
        x[i:i + 800] += np.hanning(800) * rng.normal(0, 0.6, 800)
    return x.astype(np.float32)


def babble(seed=3, secs=6.0):
    """Syllables: short voiced tones with drifting pitch and harmonics, uneven gaps. Speech rhythm, no beat."""
    r = np.random.default_rng(seed)
    x = np.zeros(int(secs * SR), np.float32)
    i = 0
    while i < len(x):
        n = int(r.uniform(0.08, 0.3) * SR)
        f0 = r.uniform(100, 220) * np.linspace(1.0, r.uniform(0.85, 1.15), n)
        ph = 2 * np.pi * np.cumsum(f0) / SR
        syl = sum(np.sin(k * ph) / k for k in range(1, 6)) * np.hanning(n) * r.uniform(0.1, 0.3)
        x[i:i + n] = syl[: len(x) - i]
        i += n + int(r.choice([r.uniform(0.03, 0.12), r.uniform(0.2, 0.6)]) * SR)
    return x


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_beat_strength_separates_beat_from_babble():
    assert beat_strength(click_track()) > 0.3
    talk = [beat_strength(babble(s)) for s in range(30)]
    # like real speech (0.06-0.27 per window on recordings): mostly below the line, the vote handles the rest
    assert np.median(talk) < 0.18 and sum(b < ears.BEAT_MUSIC for b in talk) >= 21
    assert beat_strength(babble()) < ears.BEAT_MUSIC  # the fixed one the other tests use


def test_classify_windows():
    assert classify(np.zeros(6 * SR, np.float32)) == "quiet"
    assert classify(click_track(), vad=lambda x: 1.0) == "music"  # singing over a beat is still music
    assert classify(babble(), vad=lambda x: 0.9) == "talk"
    assert classify(babble(), vad=lambda x: 0.1) == "other"
    assert classify(babble(), vad=None) == "other"


def test_vote_needs_a_majority():
    assert vote(["music", "talk", "music", "music", "music"]) == "music"
    assert vote(["talk", "music", "talk", "music", "talk"]) == "talk"
    assert vote(["music", "music", "talk", "music", "talk"]) == "music"  # a ballad's quiet verse
    assert vote(["quiet", "quiet", "quiet", "talk", "other"]) is None
    assert vote(["other", "talk", "other", "quiet", "talk"]) == "other"
    assert vote([]) is None


def test_clean_line():
    assert clean_line('"Wollah, die gast lult uit z\'n nek" 😂') == "Wollah, die gast lult uit z'n nek"
    assert clean_line("Desktop Dude: Ewa, saai man\nUitleg: ...") == "Ewa, saai man"
    assert clean_line("<think>hmm</think>Kom op zeg") == "Kom op zeg"
    assert len(clean_line("bla " * 100)) <= 110
    assert clean_line("") == ""


def test_ears_comment_pipeline_with_fakes():
    e = Ears(real=False)
    e.listen = True
    calls = []

    def http(url, body=None, timeout=120):
        calls.append((url, body))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "nomic-embed-text"}, {"name": "llama3:8b"}, {"name": "gemma4-64k:latest"},
                               {"name": "gemma4:12b"}]}
        if url.endswith("/api/ps"):
            return {"models": []}
        return {"message": {"content": '"Die vent praat echt kut, wollah"'}}

    e.http = http
    e.transcribe = lambda audio: "and that is why superintelligence would be the last invention we ever make"
    e._in_call = lambda: False
    e.chunks.extend(np.zeros(SR // 2, np.float32) for _ in range(50))
    e.title = "Superintelligence - YouTube"
    import threading

    started = []
    real_thread = threading.Thread

    class Inline(real_thread):
        def start(self):
            started.append(self)
            self.run()

    threading.Thread = Inline
    try:
        for _ in range(7):
            e._hear(babble(), vad=lambda x: 0.9)
    finally:
        threading.Thread = real_thread
    assert e.kind == "talk" and started, "should comment after 15 s of talk"
    assert e.model_name == "gemma4:12b"  # preferred over llama, embeddings skipped
    chat = next(b for u, b in calls if u.endswith("/api/chat"))
    assert "Superintelligence - YouTube" in chat["messages"][1]["content"]
    assert chat["think"] is False and chat["options"]["num_ctx"] == 2048
    assert e.pop() == "Die vent praat echt kut, wollah"
    assert e.pop() is None
    assert len(started) == 1, "and then wait a while before the next one"


def test_ears_stay_silent_during_calls_and_when_off():
    e = Ears(real=False)
    e.transcribe = lambda audio: pytest.fail("never transcribe a call")
    e._in_call = lambda: True
    e._comment(np.zeros(SR, np.float32), "")
    assert e.pop() is None and not e.busy
    e.listen = False
    e.chunks.extend(np.zeros(SR // 2, np.float32) for _ in range(50))
    for _ in range(10):
        e._hear(babble(), vad=lambda x: 0.9)
    assert e.kind == "talk" and not e.busy


def test_pick_model_prefers_what_is_already_loaded():
    e = Ears(real=False)
    tags = {"models": [{"name": "gemma4:12b"}, {"name": "qwen3.5:9b"}]}
    e.http = lambda url, body=None, timeout=120: tags if url.endswith("/tags") else {"models": [{"name": "qwen3.5:9b"}]}
    assert e.pick_model() == "qwen3.5:9b" and e.loaded


def test_old_ollama_without_think_field():
    e = Ears(real=False)
    e.model_name = "gemma4:12b"
    bodies = []

    def http(url, body=None, timeout=120):
        bodies.append(dict(body))
        if "think" in body:
            raise urllib.error.HTTPError(url, 400, "think?", {}, None)
        return {"message": {"content": "Ewa"}}

    e.http = http
    assert e.ask("bla bla bla bla bla bla") == "Ewa"
    assert "think" not in bodies[-1]


def test_podcast_is_not_music_and_comments_get_said(app):
    _w32, clock, dude = _quiet(41)
    life = dude.life
    life.music.feed = lambda t: 0.7 if (t % 0.5) < 0.04 else 0.12  # loud and beat-ish on the meter
    life.ears.kind = "talk"
    _run(dude, clock, 60 * 3)
    assert not life.music.playing, "a podcast is loud, but it's not music"
    assert not life.trigger("dance") or dude.state != "dance" or _until_stood(dude, clock)
    life.ears.kind = "music"
    _run(dude, clock, 60 * 1)
    assert life.music.playing
    life.ears.kind = None
    dude.set_state(dd.IDLE, 5.0)
    life.ears.out.put((__import__("time").time(), "Die gast lult echt uit z'n nek over die robots, wollah"))
    _run(dude, clock, 30)
    assert dude.terror.bubble is not None and dude.terror.bubble.text.startswith("Die gast lult echt")
    assert dude.terror.bubble.LIFE > 3.4


def _until_stood(dude, clock):
    for _ in range(60 * 5):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        if dude.state != "dance":
            return True
    return False


def test_config_with_bom(tmp_path, monkeypatch):
    p = tmp_path / "dude_config.json"
    p.write_bytes(b"\xef\xbb\xbf" + b'{"listen": true, "listen_model": "qwen3.5:9b"}')
    monkeypatch.setattr(ears, "CONFIG", p)
    e = Ears(real=False)
    assert e._config() == {"listen": True, "listen_model": "qwen3.5:9b"}