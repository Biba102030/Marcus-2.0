# Edge TTS — Microsoft голоса, бесплатно, через интернет
import re
import queue
import asyncio
import threading
import tempfile
import time
import os
import sys
import numpy as np
from PyQt6.QtCore import QThread
from concurrent.futures import ThreadPoolExecutor

# Фикс для Windows консоли
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

_tts_speaking = False
_tts_stop     = False
_tts_queue    = queue.Queue()

SPEED_FACTOR  = 1
VOICE         = "ru-RU-DmitryNeural"
MIN_CHUNK_LEN = 25
MAX_CHUNK_LEN = 180


def _clean_text(text: str) -> str:
    """Убираем markdown, спецсимволы и мусор перед синтезом."""
    # Блоки кода
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    # Жирный/курсив
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    # Цитаты и заголовки markdown
    text = re.sub(r'^[>#\-\*]\s*', '', text, flags=re.MULTILINE)
    # Все спецсимволы которые TTS не умеет читать
    text = re.sub(r'[◈●◌▮▯⚠⌨🎙🔊🔇🔑🎤🛑⌛\/\|№#@\*&\^~`=<>\[\]{}\\]', '', text)
    # Множественные знаки препинания
    text = re.sub(r'[!?]{2,}', '!', text)
    text = re.sub(r'\.{2,}', '.', text)
    # Лишние пробелы
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode())


def is_speaking() -> bool:
    return _tts_speaking


def stop_speaking():
    global _tts_stop, _tts_speaking
    _tts_stop     = True
    _tts_speaking = False
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except Exception:
            break
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass


def preload_silero():
    print("[TTS] Edge TTS готов, прогрев не нужен")


def _stretch_audio(audio_np: np.ndarray, speed: float) -> np.ndarray:
    if speed == 1.0:
        return audio_np
    try:
        from scipy.signal import resample_poly
        import math
        up   = 100
        down = int(round(speed * 100))
        g    = math.gcd(up, down)
        return resample_poly(audio_np, up // g, down // g).astype(np.float32)
    except ImportError:
        target_len = int(len(audio_np) / speed)
        indices    = np.linspace(0, len(audio_np) - 1, target_len)
        return np.interp(indices, np.arange(len(audio_np)), audio_np).astype(np.float32)


async def _synthesize(text: str, out_path: str):
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(out_path)


def _synth_chunk(chunk_text: str):
    """Синтезирует один кусок, возвращает (audio_np, sr) или (None, None)."""
    import soundfile as sf
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name
        asyncio.run(_synthesize(chunk_text, tmp_path))
        audio_np, sr = sf.read(tmp_path, dtype='float32')
        os.unlink(tmp_path)
        if audio_np.ndim > 1:
            audio_np = audio_np.mean(axis=1)
        return _stretch_audio(audio_np, SPEED_FACTOR), sr
    except Exception as e:
        _safe_print(f"[TTS] Ошибка синтеза: {e}")
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return None, None


def _speak(text: str):
    global _tts_speaking, _tts_stop

    text = _clean_text(text)
    if not text or len(text) < 2:
        return
    if _tts_stop:
        return

    try:
        import sounddevice as sd

        chunks = [c for c in _split_to_chunks(text, MAX_CHUNK_LEN) if c.strip()]
        if not chunks:
            return

        # Префетч: синтезируем следующий кусок пока играет текущий
        with ThreadPoolExecutor(max_workers=2) as pool:
            # Запускаем синтез всех кусков заранее (futures)
            futures = [(c, pool.submit(_synth_chunk, c)) for c in chunks]

            for chunk_text, future in futures:
                if _tts_stop:
                    break

                audio_fast, sr = future.result()  # ждём если ещё не готово
                if audio_fast is None or _tts_stop:
                    break

                _safe_print(f"[TTS] {chunk_text[:50]}")
                _tts_speaking = True
                sd.play(audio_fast, samplerate=sr)
                time.sleep(0.05)  # даём потоку запуститься

                try:
                    while sd.get_stream().active:
                        if _tts_stop:
                            sd.stop()
                            break
                        time.sleep(0.03)
                except Exception:
                    pass

        _tts_speaking = False

    except Exception as e:
        _tts_speaking = False
        _safe_print(f"[TTS] Ошибка: {e}")


def _split_to_chunks(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    result = []
    buf = text
    while len(buf) > max_len:
        cut = -1
        for m in re.finditer(r'[.!?]\s', buf[:max_len]):
            cut = m.end()
        if cut == -1:
            for m in re.finditer(r',\s', buf[:max_len]):
                cut = m.end()
        if cut == -1:
            cut = buf.rfind(' ', 0, max_len)
        if cut <= 0:
            cut = max_len
        result.append(buf[:cut].strip())
        buf = buf[cut:].strip()
    if buf:
        result.append(buf)
    return [r for r in result if r]


class TTSWorker(QThread):
    def __init__(self):
        super().__init__()
        self._running = True

    def stop(self):
        self._running = False
        _tts_queue.put(None)

    def run(self):
        global _tts_stop
        while self._running:
            item = _tts_queue.get()
            if item is None:
                continue
            _tts_stop = False
            _speak(item)


class TTSSentenceFeeder:
    FLUSH_TIMEOUT = 0.6

    def __init__(self):
        self._buf       = ""
        self._last_feed = time.time()
        self._lock      = threading.Lock()
        self._watchdog  = threading.Thread(target=self._watch, daemon=True)
        self._watchdog.start()

    def _watch(self):
        while True:
            time.sleep(0.3)
            with self._lock:
                if self._buf and (time.time() - self._last_feed) >= self.FLUSH_TIMEOUT:
                    s = _clean_text(self._buf)
                    if s:
                        _safe_print(f"[TTS>watchdog] {s[:50]}")
                        _tts_queue.put(s)
                    self._buf = ""

    def _try_split(self) -> list[str]:
        buf    = self._buf
        result = []
        while buf:
            m = re.search(r'[.!?\u2026]\s', buf)
            if m:
                chunk = buf[:m.end()].strip()
                if chunk:
                    result.append(chunk)
                buf = buf[m.end():]
                continue
            m = re.search(r',\s', buf)
            if m and m.end() >= MIN_CHUNK_LEN:
                chunk = buf[:m.end()].strip()
                if chunk:
                    result.append(chunk)
                buf = buf[m.end():]
                continue
            break
        self._buf = buf
        return result

    def feed(self, chunk: str):
        with self._lock:
            self._buf      += chunk
            self._last_feed = time.time()
            for sentence in self._try_split():
                cleaned = _clean_text(sentence)
                if cleaned:
                    _safe_print(f"[TTS>] {cleaned[:50]}")
                    _tts_queue.put(cleaned)

    def flush(self):
        with self._lock:
            s = _clean_text(self._buf)
            if s:
                _safe_print(f"[TTS>flush] {s[:50]}")
                _tts_queue.put(s)
            self._buf = ""