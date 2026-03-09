# главное окно
import os
import subprocess
import numpy as np

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from styles import (
    BG_DEEP, BG_PANEL, ACCENT, ACCENT_DIM, TEXT_DIM, RED_ACCENT, ORANGE,
    STYLE_MAIN, STYLE_INPUT, STYLE_SEND,
    STYLE_MIC_IDLE, STYLE_MIC_REC, STYLE_TTS_ON, STYLE_TTS_OFF,
    mode_btn_style
)
from widgets import MessageBubble, TypingIndicator, SidePanel, WaveformWidget
from tts import TTSWorker, TTSSentenceFeeder, preload_silero
from stt import VoiceRecordWorker
from ai_worker import MarcusWorker
from config import CHROME_PATH, MARCUS_DIR
from wake_word import WakeWordDetector

STOP_WORDS = {"стоп", "stop", "остановись", "замолчи", "хватит", "тихо"}


class MarcusWindow(QMainWindow):

    MODE_TEXT  = "text"
    MODE_VOICE = "voice"
    voice_phrase_ready = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MARCUS // AI TERMINAL")
        self.resize(1060, 700)
        self.setMinimumSize(800, 540)
        self.setStyleSheet(STYLE_MAIN)

        self._mode               = self.MODE_TEXT
        self._current_bot_bubble = None
        self._worker             = None
        self._tts_enabled        = True
        self._sample_rate        = 16000
        self._tts_feeder         = TTSSentenceFeeder()
        self._tts_thread         = TTSWorker()
        self._tts_thread.start()

        self._voice_active      = False
        self._is_speaking       = False
        self._audio_frames      = []
        self._sd_stream         = None
        self._waiting_for_reply = False

        self._build_ui()
        self.voice_phrase_ready.connect(self._on_voice_phrase)
        self._preload_tts()
        self._show_welcome()

        self._wake_detector = WakeWordDetector()
        self._wake_detector.wake_detected.connect(self._on_wake_word)
        self._wake_detector.start()

    # ── Построение UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        root.setStyleSheet(f"background-color: {BG_DEEP};")
        self.setCentralWidget(root)

        main = QVBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        main.addWidget(self._build_header())

        # Тело — боковая панель + чат
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.side_panel = SidePanel()
        body.addWidget(self.side_panel)
        body.addWidget(self._build_chat(), 1)

        body_widget = QWidget()
        body_widget.setLayout(body)
        main.addWidget(body_widget, 1)

        main.addWidget(self._build_separator())
        main.addWidget(self._build_input_bar())

        self._update_mode_ui()

    def _build_header(self):
        header = QFrame()
        header.setFixedHeight(62)
        header.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; "
            f"border-bottom: 1px solid {ACCENT_DIM}; }}"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 24, 0)
        hl.setSpacing(8)

        self.btn_text = QPushButton("⌨  ТЕКСТ")
        self.btn_text.setFixedHeight(34)
        self.btn_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_text.clicked.connect(lambda: self._set_mode(self.MODE_TEXT))

        self.btn_voice = QPushButton("🎙  ГОЛОС")
        self.btn_voice.setFixedHeight(34)
        self.btn_voice.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_voice.clicked.connect(lambda: self._set_mode(self.MODE_VOICE))

        logo = QLabel("◈  MARCUS")
        logo.setFont(QFont("Consolas", 15, QFont.Weight.Bold))
        logo.setStyleSheet(f"color: {ACCENT}; letter-spacing: 5px; background: transparent;")

        self.status_dot = QLabel("● ONLINE")
        self.status_dot.setFont(QFont("Consolas", 9))
        self.status_dot.setStyleSheet(
            f"color: {ACCENT}; letter-spacing: 2px; background: transparent;"
        )

        self.model_label = QLabel("")
        self.model_label.setFont(QFont("Consolas", 8))
        self.model_label.setStyleSheet(f"color: {TEXT_DIM}; background: transparent;")

        hl.addWidget(self.btn_text)
        hl.addWidget(self.btn_voice)
        hl.addStretch()
        hl.addWidget(self.model_label)
        hl.addSpacing(12)
        hl.addWidget(logo)
        hl.addSpacing(16)
        hl.addWidget(self.status_dot)
        return header

    def _build_chat(self):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"background-color: {BG_DEEP}; border: none;")

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet(f"background-color: {BG_DEEP};")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(28, 20, 28, 20)
        self.chat_layout.setSpacing(10)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.typing = TypingIndicator()
        self.typing.hide()
        self.chat_layout.addWidget(self.typing)

        self.scroll.setWidget(self.chat_container)
        return self.scroll

    def _build_separator(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {ACCENT_DIM};")
        return sep

    def _build_input_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        bar.setFixedHeight(72)
        il = QHBoxLayout(bar)
        il.setContentsMargins(16, 12, 16, 12)
        il.setSpacing(10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Введи команду, Босс...")
        self.input_field.setStyleSheet(STYLE_INPUT)
        self.input_field.setFixedHeight(46)
        self.input_field.returnPressed.connect(self._send_text)

        self.send_btn = QPushButton("SEND ▶")
        self.send_btn.setStyleSheet(STYLE_SEND)
        self.send_btn.setFixedSize(100, 46)
        self.send_btn.clicked.connect(self._send_text)

        # Waveform заменяет кнопку ГОЛОС при записи
        self.waveform = WaveformWidget()
        self.waveform.setFixedHeight(46)
        self.waveform.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.waveform.hide()

        self.mic_btn = QPushButton("🎙 ГОЛОС: ВЫКЛ")
        self.mic_btn.setStyleSheet(STYLE_MIC_IDLE)
        self.mic_btn.setFixedHeight(46)
        self.mic_btn.setMinimumWidth(160)
        self.mic_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.mic_btn.clicked.connect(self._toggle_voice)

        self.tts_btn = QPushButton("🔊 TTS: ВКЛ")
        self.tts_btn.setFixedSize(120, 46)
        self.tts_btn.setStyleSheet(STYLE_TTS_ON)
        self.tts_btn.clicked.connect(self._toggle_tts)

        il.addWidget(self.input_field)
        il.addWidget(self.send_btn)
        il.addWidget(self.mic_btn)
        il.addWidget(self.waveform)
        il.addWidget(self.tts_btn)
        return bar

    # ── Адаптивные отступы ────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        margin = int(w * 0.04) if w >= 1100 else 20
        self.chat_layout.setContentsMargins(margin, 20, margin, 20)

        # Боковая панель масштабируется только в полноэкранном режиме
        if self.isMaximized() or self.isFullScreen():
            scale = min(w / 1060, 1.3)
        else:
            scale = 1.0  # оконный режим — базовые размеры
        self.side_panel.scale(scale)

    # ── Wake word ─────────────────────────────────────────────────────────────
    def _on_wake_word(self):
        if not self.isVisible() or self.isMinimized():
            self.show()
            self.raise_()
            self.activateWindow()
        self._set_mode(self.MODE_VOICE)
        if not self._voice_active:
            self._start_voice_mode()
        self._set_status("● МАРКУС СЛЫШИТ", ACCENT)

    # ── Режим текст / голос ───────────────────────────────────────────────────
    def _set_mode(self, mode):
        self._mode = mode
        self._update_mode_ui()

    def _update_mode_ui(self):
        is_text = self._mode == self.MODE_TEXT
        self.btn_text.setStyleSheet(mode_btn_style(is_text))
        self.btn_voice.setStyleSheet(mode_btn_style(not is_text))
        self.input_field.setVisible(True)
        self.send_btn.setVisible(True)
        self.mic_btn.setVisible(not is_text)
        self.tts_btn.setVisible(not is_text)
        self.side_panel.set_module_status("VOICE", not is_text)

    def _toggle_tts(self):
        from tts import stop_speaking
        self._tts_enabled = not self._tts_enabled
        if self._tts_enabled:
            self.tts_btn.setText("🔊 TTS: ВКЛ")
            self.tts_btn.setStyleSheet(STYLE_TTS_ON)
        else:
            stop_speaking()
            self.tts_btn.setText("🔇 TTS: ВЫКЛ")
            self.tts_btn.setStyleSheet(STYLE_TTS_OFF)
        self.side_panel.set_module_status("TTS", self._tts_enabled)

    # ── Голосовой режим ───────────────────────────────────────────────────────
    def _toggle_voice(self):
        if self._voice_active:
            self._stop_voice_mode()
        else:
            self._start_voice_mode()

    def _start_voice_mode(self):
        try:
            import sounddevice as sd
        except ImportError:
            self._add_error_message("Установи: pip install sounddevice soundfile")
            return

        import sounddevice as sd
        self._voice_active      = True
        self._is_speaking       = False
        self._audio_frames      = []
        self._waiting_for_reply = False

        # Показываем waveform вместо кнопки
        self.mic_btn.hide()
        self.waveform.show()
        self.waveform.start()

        self._set_status("● СЛУШАЮ", ACCENT)
        self._wake_detector.pause()
        self.side_panel.set_module_status("VOICE", True)

        SILENCE_THRESHOLD     = 0.015
        SILENCE_SECS          = 3.0
        self._last_sound_time = __import__('time').time()

        def callback(indata, frames, time_info, status):
            from tts import is_speaking
            if not self._voice_active or self._waiting_for_reply or is_speaking():
                return
            volume = float(np.abs(indata).mean())
            self.waveform.update_bars(volume)
            now = __import__('time').time()
            if volume > SILENCE_THRESHOLD:
                self._last_sound_time = now
                self._is_speaking     = True
                self._audio_frames.append(indata.copy())
            else:
                if self._is_speaking:
                    self._audio_frames.append(indata.copy())
                    elapsed = now - self._last_sound_time
                    if elapsed >= SILENCE_SECS and self._audio_frames:
                        frames_copy             = list(self._audio_frames)
                        self._audio_frames      = []
                        self._is_speaking       = False
                        self._waiting_for_reply = True
                        self._pending_frames    = frames_copy
                        self.voice_phrase_ready.emit()

        self._sd_stream = sd.InputStream(
            samplerate=self._sample_rate, channels=1,
            dtype='float32', blocksize=1024, callback=callback
        )
        self._sd_stream.start()

    def _stop_voice_mode(self):
        from tts import stop_speaking
        stop_speaking()
        self._voice_active = False
        self._is_speaking  = False
        self._audio_frames = []
        if self._sd_stream:
            self._sd_stream.stop()
            self._sd_stream.close()
            self._sd_stream = None

        self.waveform.stop()
        self.waveform.hide()
        self.mic_btn.show()
        self.mic_btn.setStyleSheet(STYLE_MIC_IDLE)
        self.mic_btn.setText("🎙 ГОЛОС: ВЫКЛ")
        self._set_status("● ONLINE", ACCENT)
        self._wake_detector.resume()
        self.side_panel.set_module_status("VOICE", False)

    def _on_voice_phrase(self):
        if not hasattr(self, '_pending_frames') or not self._pending_frames:
            self._waiting_for_reply = False
            return
        frames               = self._pending_frames
        self._pending_frames = []
        self._set_status("◌ STT", ORANGE)
        audio_data         = np.concatenate(frames, axis=0).flatten()
        self._voice_worker = VoiceRecordWorker(audio_data, self._sample_rate)
        self._voice_worker.transcription_ready.connect(self._on_transcription)
        self._voice_worker.error_signal.connect(self._on_voice_error)
        self._voice_worker.start()

    def _on_transcription(self, text: str):
        from tts import stop_speaking
        words = set(text.lower().strip().rstrip(".!?").split())
        if words & STOP_WORDS:
            stop_speaking()
            self._waiting_for_reply = False
            if self._voice_active:
                self._set_status("● СЛУШАЮ", ACCENT)
            self._add_bot_message("Остановил, Босс. Слушаю.")
            return
        self._add_user_message(f"🎙 {text}")
        self._run_marcus(text)

    def _on_voice_error(self, msg: str):
        self._waiting_for_reply = False
        self._set_status("● СЛУШАЮ" if self._voice_active else "● ONLINE", ACCENT)
        self._add_error_message(msg)

    # ── Текстовый ввод ────────────────────────────────────────────────────────
    def _send_text(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        tl = text.lower()
        shortcuts = {
            ("музыка.", "музыка"): (
                lambda: subprocess.Popen([CHROME_PATH, "https://music.yandex.uz/"]),
                "Музыка открыта в Chrome, Босс."
            ),
            ("код.", "открой код", "vscode"): (
                lambda: subprocess.run(["code", MARCUS_DIR]),
                "Папка открыта в VS Code, Босс."
            ),
        }
        for keys, (action, reply) in shortcuts.items():
            if tl in keys:
                action()
                self._add_user_message(text)
                self._add_bot_message(reply)
                return
        if tl == "браузер.":
            subprocess.Popen([CHROME_PATH])
            self._add_user_message(text)
            self._add_bot_message("Chrome открыт, Босс.")
            return
        self._add_user_message(text)
        self._run_marcus(text)

    # ── Ядро — запуск LLM ─────────────────────────────────────────────────────
    def _run_marcus(self, text: str):
        self._set_input_enabled(False)
        self.typing.start()
        self._current_bot_bubble = None
        self._wake_detector.pause()
        self.side_panel.set_module_status("AI", True)
        self._worker = MarcusWorker(text)
        self._worker.token_ready.connect(self._on_token)
        self._worker.reply_done.connect(self._on_done)
        self._worker.error_signal.connect(self._on_error)
        self._worker.start()

    def _on_token(self, chunk: str):
        if self._current_bot_bubble is None:
            self.typing.stop()
            self._current_bot_bubble = self._add_bot_message("")
        self._current_bot_bubble.append_text(chunk)
        self._scroll_to_bottom()
        if self._tts_enabled:
            self._tts_feeder.feed(chunk)

    def _on_done(self, model: str, full_text: str):
        self.typing.stop()
        self.model_label.setText(f"[ {model.split('/')[-1]} ]")
        self._set_input_enabled(True)
        self._current_bot_bubble = None
        self.side_panel.set_module_status("AI", False)
        if self._tts_enabled:
            self._tts_feeder.flush()
        if self._mode == self.MODE_VOICE and self._voice_active:
            self._waiting_for_reply = False
            self._is_speaking       = False
            self._audio_frames      = []
            self._set_status("● СЛУШАЮ", ACCENT)
        else:
            self._set_status("● ONLINE", ACCENT)
            self._wake_detector.resume()
        if self._mode == self.MODE_TEXT:
            self.input_field.setFocus()

    def _on_error(self, msg: str):
        self.typing.stop()
        self._add_error_message(msg)
        self._set_input_enabled(True)
        self._current_bot_bubble = None
        self._set_status("● ONLINE", ACCENT)
        self.side_panel.set_module_status("AI", False)
        self._wake_detector.resume()

    # ── Хелперы ───────────────────────────────────────────────────────────────
    def _add_user_message(self, text: str):
        b = MessageBubble(text, is_user=True)
        self.chat_layout.addWidget(b)
        self._scroll_to_bottom()

    def _add_bot_message(self, text: str) -> MessageBubble:
        b = MessageBubble(text, is_user=False)
        self.chat_layout.addWidget(b)
        self._scroll_to_bottom()
        return b

    def _add_error_message(self, text: str):
        lbl = QLabel(f"⚠ {text}")
        lbl.setFont(QFont("Consolas", 10))
        lbl.setStyleSheet(f"color: {RED_ACCENT}; background: transparent; padding: 4px 0;")
        lbl.setWordWrap(True)
        self.chat_layout.addWidget(lbl)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))

    def _set_status(self, text: str, color: str):
        self.status_dot.setText(text)
        self.status_dot.setStyleSheet(
            f"color: {color}; letter-spacing: 2px; background: transparent;"
        )

    def _set_input_enabled(self, enabled: bool):
        self.input_field.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)
        if self._mode == self.MODE_TEXT:
            self.mic_btn.setEnabled(enabled)
        if not enabled:
            self._set_status("◌ THINKING", ORANGE)

    def _preload_tts(self):
        preload_silero()

    def _show_welcome(self):
        self._add_bot_message(
            "Система инициализирована. Маркус на связи, Босс.\n\n"
            "⌨  ТЕКСТ — печатай запросы, жми Enter\n"
            "🎙  ГОЛОС — нажми один раз, говори, пауза 3 сек → отправит\n"
            "🔊  TTS — включает голосовые ответы Маркуса\n"
            "🛑  Скажи 'стоп' или 'замолчи' — Маркус замолкает мгновенно\n"
            "🔑  Ctrl+Shift+M — показать/скрыть окно\n"
            "🎤  Скажи 'Маркус' — активирует голосовой режим автоматически"
        )