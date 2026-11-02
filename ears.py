"""The dude's ears: is your PC playing music or people talking? And, if you switch it on, what are they saying?

Everything stays on this PC. Sound comes from the speaker loopback into memory only, gets classified with numpy
and Silero VAD, transcribed by a local Whisper model and commented on by a local Ollama model. Nothing is written
to disk and nothing leaves the machine. Calls (Teams, Discord, Zoom, ...) are never transcribed.

Music vs talk, measured on real clips: music has a periodic onset pattern (autocorrelation of the spectral flux at
0.25-1.2 s lags: 0.26-0.56 for songs, 0.07-0.20 for speech), speech has voice activity. One 6 s window can be
fooled (a ballad's quiet verse), so the label is a vote over the last five windows.
"""

from __future__ import annotations

import collections
import json
import queue
import re
import threading
import time
import urllib.error
import urllib.request

import numpy as np

from appdir import DATA
from terror import _log

SR = 16000
WIN = 6.0  # seconds per classification window
EVERY = 3.0  # classify this often
VOTES = 5  # vote over the last 5 windows (~18 s)
BEAT_MUSIC = 0.22
QUIET = 0.004  # rms below this is silence
TALK_BEFORE_COMMENT = 15.0  # seconds of talk before the first comment
GAP = (75.0, 150.0)  # seconds between comments
CLIP = 20.0  # seconds of audio he listens to for one comment
FRESH = 25.0  # a comment older than this is stale
CALL_APPS = re.compile(r"teams|discord|zoom|slack|skype|webex|signal|whatsapp|telegram|facetime", re.IGNORECASE)
OLLAMA = "http://127.0.0.1:11434"
PREFER = ("gemma", "qwen", "llama", "mistral", "phi")
CONFIG = DATA / "dude_config.json"

SYSTEM = (
    "Je bent Desktop Dude, een klein brutaal stokpoppetje dat op iemands bureaublad woont. Je hoort mee met de "
    "video of podcast die hij kijkt. Reageer met EEN korte zin (hooguit 12 woorden) in Amsterdamse straattaal, "
    "grappig en brutaal, op wat er net gezegd wordt. Geen uitleg, geen aanhalingstekens, geen emoji, geen hashtags."
)


# ---------------------------------------------------------------- analysis (pure, testable)
def beat_strength(x: np.ndarray) -> float:
    """How periodic the onsets are: autocorrelation peak of the spectral flux at 0.25-1.2 s lags."""
    hop, win = 160, 400
    if len(x) < win + hop * 130:
        return 0.0
    x = np.ascontiguousarray(x, dtype=np.float32)
    n = 1 + (len(x) - win) // hop
    fr = np.lib.stride_tricks.as_strided(x, (n, win), (x.strides[0] * hop, x.strides[0]))
    logs = np.log1p(np.abs(np.fft.rfft(fr * np.hanning(win).astype(np.float32), axis=1)) * 10)
    flux = np.maximum(0, np.diff(logs, axis=0)).sum(1)
    flux = flux - flux.mean()
    ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
    return float(ac[25:120].max() / (ac[0] + 1e-9))


def classify(x: np.ndarray, vad=None) -> str:
    """One window -> quiet / music / talk / other. vad(x) returns the fraction of x that is speech."""
    if float(np.sqrt(np.mean(np.square(x)))) < QUIET:
        return "quiet"
    if beat_strength(x) >= BEAT_MUSIC:
        return "music"
    if vad is not None and vad(x) > 0.5:
        return "talk"
    return "other"


def vote(labels) -> str | None:
    labels = list(labels)[-VOTES:]
    if labels.count("talk") >= 3:
        return "talk"
    if labels.count("music") >= 2:
        return "music"
    if not labels or labels.count("quiet") >= 3:
        return None
    return "other"


def silero(x: np.ndarray) -> float:
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    ts = get_speech_timestamps(np.ascontiguousarray(x, dtype=np.float32), VadOptions(min_silence_duration_ms=300))
    return sum(t["end"] - t["start"] for t in ts) / max(1, len(x))


def clean_line(text: str) -> str:
    """First real line of what the model said, without quotes, speaker labels, emoji or a novel."""
    for line in (text or "").splitlines():
        line = re.sub(r"<think>.*?</think>", "", line).strip()
        line = re.sub(r"^(desktop\s*dude|dude)\s*:\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"[\U0001F000-\U0001FFFF☀-➿#*_]", "", line).strip(" \"'“”‘’")
        if len(line) >= 3:
            if len(line) > 110:
                line = line[:107].rsplit(" ", 1)[0] + "..."
            return line
    return ""


def _http_json(url, body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------- the ears
class Ears:
    def __init__(self, real):
        self.real = real
        self.labels: collections.deque = collections.deque(maxlen=VOTES)
        self.kind: str | None = None
        self.title = ""
        self.out: queue.Queue = queue.Queue()
        self.http = _http_json
        self.listen = bool(self._config().get("listen", False)) if real else False
        self.model_name = self._config().get("listen_model") if real else None
        self.problem = ""  # why commenting doesn't work, for the tray
        self.talk_for = 0.0
        self.next_comment = 0.0
        self.busy = False
        self.said: collections.deque = collections.deque(maxlen=3)
        self.chunks: collections.deque = collections.deque(maxlen=int(CLIP * 2) + 4)  # 0.5 s chunks
        self._whisper = None
        self.loaded = False  # the model was already running: don't touch its context size
        self._stop = threading.Event()
        if real:
            threading.Thread(target=self._capture_loop, daemon=True, name="ears").start()

    # ---- settings
    def _config(self) -> dict:
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
        except (OSError, ValueError):
            return {}

    def set_listen(self, on: bool):
        self.listen = bool(on)
        self.problem = ""
        if not self.real:
            return
        cfg = self._config()
        cfg["listen"] = self.listen
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
        except OSError as e:
            _log(f"ears: can't save setting: {e!r}")
        if self.listen:
            threading.Thread(target=self._check_ollama, daemon=True).start()

    @property
    def status(self) -> str:
        hears = {"music": "music", "talk": "talking", "other": "sound", None: "silence"}[self.kind]
        if not self.listen:
            return f"Ears: {hears} · commenting off"
        if self.problem:
            return f"Ears: {hears} · {self.problem}"
        return f"Ears: {hears} · commenting via {self.model_name or 'Ollama'}"

    # ---- main thread
    def pop(self) -> str | None:
        while True:
            try:
                t, line = self.out.get_nowait()
            except queue.Empty:
                return None
            if time.time() - t < FRESH:
                return line

    def stop(self):
        self._stop.set()

    # ---- capture thread
    def _capture_loop(self):
        import warnings

        warnings.filterwarnings("ignore", message="data discontinuity")  # dropped packets while Whisper runs
        try:
            import soundcard as sc
        except Exception as e:  # noqa: BLE001 - no soundcard: he can't tell music from talk, nothing else breaks
            _log(f"ears disabled: {e!r}")
            return
        vad = None
        while not self._stop.is_set():
            try:
                if vad is None:
                    try:
                        silero(np.zeros(SR, np.float32))
                        vad = silero
                    except Exception as e:  # noqa: BLE001
                        _log(f"ears: no voice detection ({e!r}), music detection only")
                        vad = False
                spk = sc.default_speaker()
                mic = sc.get_microphone(spk.id, include_loopback=True)
                with mic.recorder(samplerate=SR, channels=1, blocksize=SR // 10) as rec:
                    opened, since = time.time(), 0.0
                    while not self._stop.is_set() and time.time() - opened < 60:  # follow default-device changes
                        a = rec.record(numframes=SR // 2)
                        a = a.mean(axis=1) if a.ndim > 1 else a
                        self.chunks.append(np.asarray(a, np.float32))
                        since += 0.5
                        if since >= EVERY and len(self.chunks) >= WIN * 2:
                            since = 0.0
                            self._hear(self.recent(WIN), vad or None)
            except Exception as e:  # noqa: BLE001 - device gone, driver hiccup: try again in a bit
                _log(f"ears: capture error {e!r}")
                self._stop.wait(5.0)

    def recent(self, secs) -> np.ndarray:
        n = int(secs * 2)
        chunks = list(self.chunks)[-n:]
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)

    def _hear(self, window, vad):
        self.labels.append(classify(window, vad))
        self.kind = vote(self.labels)
        self.talk_for = self.talk_for + EVERY if self.kind == "talk" else 0.0
        now = time.time()
        if (self.listen and not self.busy and self.kind == "talk" and self.talk_for >= TALK_BEFORE_COMMENT
                and now >= self.next_comment):
            self.busy = True
            self.next_comment = now + np.random.uniform(*GAP)
            audio, title = self.recent(CLIP), self.title
            threading.Thread(target=self._comment, args=(audio, title), daemon=True).start()

    # ---- worker
    def _comment(self, audio, title):
        try:
            if self._in_call():
                return
            text = self.transcribe(audio)
            if len(text.split()) < 6:
                return
            line = self.ask(text, title)
            if line:
                self.out.put((time.time(), line))
        except Exception as e:  # noqa: BLE001
            _log(f"ears: comment failed {e!r}")
        finally:
            self.busy = False

    def _in_call(self) -> bool:
        try:
            import comtypes
            from pycaw.pycaw import AudioUtilities

            comtypes.CoInitialize()
            try:
                for s in AudioUtilities.GetAllSessions():
                    if s.Process is not None and s.State == 1 and CALL_APPS.search(s.Process.name()):
                        return True
            finally:
                comtypes.CoUninitialize()
        except Exception as e:  # noqa: BLE001 - can't tell: play safe
            _log(f"ears: session check failed {e!r}")
            return True
        return False

    def transcribe(self, audio) -> str:
        if self._whisper is None:
            from faster_whisper import WhisperModel

            _log("ears: loading Whisper (first time downloads ~480 MB)")
            self._whisper = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4,
                                         download_root=str(DATA / "models"))
        segs, _ = self._whisper.transcribe(np.ascontiguousarray(audio, np.float32), beam_size=1, vad_filter=True,
                                           condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip()

    def pick_model(self) -> str | None:
        """Your choice (listen_model in dude_config.json), else a chat model that's already loaded (costs no
        extra VRAM), else the first gemma/qwen/llama/... you have, preferring plain tags over custom variants."""
        tags = self.http(OLLAMA + "/api/tags", timeout=5).get("models", [])
        names = [m["name"] for m in tags if "embed" not in m["name"]]
        self.loaded = False
        if self.model_name in names:
            return self.model_name
        try:
            running = [m["name"] for m in self.http(OLLAMA + "/api/ps", timeout=5).get("models", [])]
        except Exception:  # noqa: BLE001
            running = []
        for n in running:
            if n in names:
                self.loaded = True
                return n
        for p in PREFER:
            hits = [n for n in names if n.lower().startswith(p)]
            hits.sort(key=lambda n: ("-" in n.split(":")[0], n))  # gemma4:12b before gemma4-64k:latest
            if hits:
                return hits[0]
        return names[0] if names else None

    def _check_ollama(self):
        try:
            self.model_name = self.pick_model()
            self.problem = "" if self.model_name else "no Ollama model (ollama pull gemma3)"
        except Exception:  # noqa: BLE001
            self.problem = "Ollama not running (ollama.com)"

    def ask(self, text, title="") -> str:
        if not self.model_name:
            self._check_ollama()
            if not self.model_name:
                return ""
        msg = f"Ze zeggen: {text[-900:]}"
        if title:
            msg = f"Venster: {title[:120]}\n" + msg
        if self.said:
            msg += "\nJe zei eerder al: " + " | ".join(self.said) + " (herhaal jezelf niet)"
        body = {"model": self.model_name, "stream": False, "think": False, "keep_alive": "10m",
                "options": {"temperature": 0.95, "num_predict": 48} | ({} if self.loaded else {"num_ctx": 2048}),
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": msg}]}
        try:
            try:
                r = self.http(OLLAMA + "/api/chat", body)
            except urllib.error.HTTPError as e:
                if e.code != 400:
                    raise
                body.pop("think")  # an older Ollama, or a model that doesn't know the field
                r = self.http(OLLAMA + "/api/chat", body)
        except Exception:
            self.problem = "Ollama not reachable"
            raise
        self.problem = ""
        line = clean_line(r.get("message", {}).get("content", ""))
        if line:
            self.said.append(line)
        return line
