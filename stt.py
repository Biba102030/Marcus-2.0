# Groq Whisper STT — авто-определение языка (ru + en)
import os
import tempfile
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from groq import Groq


class VoiceRecordWorker(QThread):
    transcription_ready = pyqtSignal(str)
    error_signal        = pyqtSignal(str)

    def __init__(self, audio_data: np.ndarray, sample_rate: int):
        super().__init__()
        self.audio_data  = audio_data
        self.sample_rate = sample_rate

    def run(self):
        try:
            import soundfile as sf

            print("[STT] Сохраняю аудио...")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name
            sf.write(tmp_path, self.audio_data, self.sample_rate)

            print("[STT] Отправляю в Groq Whisper API...")
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            with open(tmp_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=("audio.wav", audio_file.read()),
                    model="whisper-large-v3-turbo",
                    # language убран — Whisper сам определит ru/en/любой
                    response_format="text"
                )
            os.unlink(tmp_path)

            text = (
                transcription.strip()
                if isinstance(transcription, str)
                else transcription.text.strip()
            )
            print(f"[STT] Результат: {repr(text)}")

            if text:
                self.transcription_ready.emit(text)
            else:
                self.error_signal.emit("Не удалось распознать речь.")

        except Exception as e:
            import traceback
            print(f"[STT] Ошибка: {e}")
            traceback.print_exc()
            self.error_signal.emit(f"Ошибка STT: {e}")