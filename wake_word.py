# Wake word детектор — "Маркус" / "Marcus"
import os
import time
import threading
import tempfile
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

WAKE_WORDS = {
    "маркус", "marcus","marcos", "маркуса", "маркусе",
    "эй маркус", "эй маркуса", "hey marcus", "ei markus",
    "ей маркус", "arkus", "markus"
}
CHUNK_SECS  = 2.0
SAMPLE_RATE = 16000
VOLUME_MIN  = 0.008


class WakeWordDetector(QObject):
    wake_detected = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._running = False
        self._paused  = False
        self._thread  = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[WAKE] Детектор запущен — скажи 'Маркус'")

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def _loop(self):
        try:
            import sounddevice as sd
        except ImportError:
            print("[WAKE] Нет sounddevice — wake word не работает")
            return

        import sounddevice as sd

        while self._running:
            if self._paused:
                time.sleep(0.2)
                continue
            try:
                frames    = int(SAMPLE_RATE * CHUNK_SECS)
                audio     = sd.rec(frames, samplerate=SAMPLE_RATE,
                                   channels=1, dtype='float32')
                sd.wait()
                audio_flat = audio.flatten()

                volume = float(np.abs(audio_flat).mean())
                if volume < VOLUME_MIN:
                    continue

                text = self._transcribe(audio_flat)
                if not text:
                    continue

                print(f"[WAKE] Слышу: {text!r}")
                cleaned = text.lower().strip().rstrip(".!?")
                words   = set(cleaned.split())
                if words & WAKE_WORDS or any(w in cleaned for w in WAKE_WORDS):
                    print("[WAKE] Wake word обнаружен!")
                    self._paused = True
                    self.wake_detected.emit()

            except Exception as e:
                print(f"[WAKE] Ошибка: {e}")
                time.sleep(1)

    def _transcribe(self, audio_np: np.ndarray) -> str:
        try:
            import soundfile as sf
            from groq import Groq

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name
            sf.write(tmp_path, audio_np, SAMPLE_RATE)

            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            with open(tmp_path, "rb") as af:
                result = client.audio.transcriptions.create(
                    file=("audio.wav", af.read()),
                    model="whisper-large-v3-turbo",
                    response_format="text"
                )
            os.unlink(tmp_path)
            return result.strip() if isinstance(result, str) else result.text.strip()
        except Exception as e:
            print(f"[WAKE] Transcribe error: {e}")
            return ""