# MessageBubble, TypingIndicator, SidePanel, WaveformWidget
import math

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QWidget
)
from PyQt6.QtCore import Qt, QTimer, QThread
from PyQt6.QtGui import QFont, QPainter, QColor
from PyQt6.QtCore import pyqtSignal

from styles import (
    ACCENT, ACCENT2, ACCENT_DIM, TEXT_MAIN, TEXT_DIM,
    MSG_USER, MSG_BOT, BG_SIDE, ORANGE, RED_ACCENT,
    FONT_MONO, FONT_TEXT
)

# Базовые размеры — масштабируются при resizeEvent окна
BASE_SIDE_W      = 170
BASE_TIME_SIZE   = 17
BASE_STAT_SIZE   = 16
BASE_LABEL_SIZE  = 10
BASE_MOD_SIZE    = 11
BASE_MSG_SIZE    = 13
BASE_HEADER_SIZE = 9


# ── MessageBubble ─────────────────────────────────────────────────────────────
class MessageBubble(QFrame):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self._build(text)

    def _build(self, text: str):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(3)
        self.setStyleSheet("background: transparent;")

        # Метка отправителя — моноширинный
        header = QLabel("БОСС" if self.is_user else "MARCUS")
        header.setFont(QFont("Consolas", BASE_HEADER_SIZE, QFont.Weight.Bold))
        header.setStyleSheet(
            f"color: {'#0088FF' if self.is_user else ACCENT}; "
            f"letter-spacing: 3px; background: transparent;"
        )

        # Пузырь
        bubble = QFrame()
        bubble.setObjectName("bubble")
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(14, 10, 14, 10)

        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        # Segoe UI для читаемости текста сообщений
        self.text_label.setFont(QFont("Segoe UI", BASE_MSG_SIZE))
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text_label.setStyleSheet(f"color: {TEXT_MAIN}; background: transparent; line-height: 150%;")
        self.text_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        bl.addWidget(self.text_label)

        if self.is_user:
            bubble.setStyleSheet(
                f"QFrame#bubble {{ background-color: {MSG_USER}; "
                f"border: 1px solid {ACCENT2}; border-radius: 12px; border-top-right-radius: 3px; }}"
            )
        else:
            bubble.setStyleSheet(
                f"QFrame#bubble {{ background-color: {MSG_BOT}; "
                f"border: 1px solid {ACCENT_DIM}; border-radius: 12px; border-top-left-radius: 3px; }}"
            )

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if self.is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()

        outer.addWidget(header)
        outer.addLayout(row)

    def append_text(self, chunk: str):
        self.text_label.setText(self.text_label.text() + chunk)

    def scale_fonts(self, factor: float):
        size = max(10, int(BASE_MSG_SIZE * factor))
        self.text_label.setFont(QFont("Segoe UI", size))


# ── TypingIndicator ───────────────────────────────────────────────────────────
class TypingIndicator(QLabel):
    def __init__(self):
        super().__init__()
        self.dots = 0
        self.setFont(QFont("Consolas", 11))
        self.setStyleSheet(f"color: {ACCENT}; background: transparent; padding: 8px 0;")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self.dots = 0
        self._timer.start(400)
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self.dots = (self.dots + 1) % 4
        self.setText("MARCUS" + " ▮" * self.dots + " ▯" * (3 - self.dots))


# ── WaveformWidget ────────────────────────────────────────────────────────────
class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._bars   = [0.0] * 24
        self._active = False
        self._timer  = QTimer(self)
        self._timer.timeout.connect(self._animate_idle)
        self._phase  = 0.0

    def start(self):
        self._active = True
        self._timer.start(60)
        self.show()

    def stop(self):
        self._active = False
        self._timer.stop()
        self._bars = [0.0] * 24
        self.update()
        self.hide()

    def update_bars(self, volume: float):
        if not self._active:
            return
        self._bars = self._bars[1:] + [min(volume * 10, 1.0)]
        self.update()

    def _animate_idle(self):
        self._phase += 0.15
        for i in range(len(self._bars)):
            self._bars[i] = max(0.05, abs(math.sin(self._phase + i * 0.4)) * 0.25)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        n, gap = len(self._bars), 3
        bw = max(2, (w - gap * (n - 1)) // n)
        for i, amp in enumerate(self._bars):
            bar_h = max(3, int(amp * (h - 8)))
            x = i * (bw + gap)
            y = (h - bar_h) // 2
            color = QColor(ACCENT)
            color.setAlpha(int(80 + 175 * amp))
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bw, bar_h, 2, 2)


# ── SysMonitorThread ──────────────────────────────────────────────────────────
class SysMonitorThread(QThread):
    stats_ready = pyqtSignal(float, float, float)

    def __init__(self):
        super().__init__()
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        import psutil, subprocess
        while self._running:
            cpu = psutil.cpu_percent(interval=1.5)
            ram = psutil.virtual_memory().percent
            gpu = -1.0
            try:
                r = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0:
                    gpu = float(r.stdout.strip().split("\n")[0])
            except Exception:
                pass
            self.stats_ready.emit(cpu, ram, gpu)


# ── SidePanel ─────────────────────────────────────────────────────────────────
class SidePanel(QFrame):

    # Базовые размеры шрифтов — масштабируются при resize
    _BASE_W    = BASE_SIDE_W
    _BASE_TIME = BASE_TIME_SIZE
    _BASE_STAT = BASE_STAT_SIZE
    _BASE_LBL  = BASE_LABEL_SIZE
    _BASE_MOD  = BASE_MOD_SIZE

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self._BASE_W)
        self.setStyleSheet(
            f"QFrame {{ background-color: {BG_SIDE}; border-right: 1px solid {ACCENT_DIM}; }}"
        )
        self._build()
        self._start_monitor()

    def scale(self, factor: float):
        """Масштабировать шрифты и ширину панели."""
        w = int(self._BASE_W * factor)
        self.setFixedWidth(w)

        self.time_lbl.setFont(QFont("Consolas", max(10, int(self._BASE_TIME * factor)), QFont.Weight.Bold))
        self.date_lbl.setFont(QFont("Consolas", max(6, int(self._BASE_LBL * factor))))
        self.cpu_lbl.setFont(QFont("Consolas",  max(10, int(self._BASE_STAT * factor)), QFont.Weight.Bold))
        self.ram_lbl.setFont(QFont("Consolas",  max(10, int(self._BASE_STAT * factor)), QFont.Weight.Bold))
        self.gpu_lbl.setFont(QFont("Consolas",  max(10, int(self._BASE_STAT * factor)), QFont.Weight.Bold))

        mod_size = max(7, int(self._BASE_MOD * factor))
        for _, dot, lbl in [self.mod_tts, self.mod_voice, self.mod_ai, self.mod_wake]:
            lbl.setFont(QFont("Consolas", mod_size, QFont.Weight.Bold))

    def _divider(self):
        d = QFrame()
        d.setFixedHeight(1)
        d.setStyleSheet(f"background: {ACCENT_DIM}; margin: 3px 0;")
        return d

    def _bar_widget(self):
        b = QFrame()
        b.setFixedHeight(3)
        b.setStyleSheet(f"background: {ACCENT_DIM}; border-radius: 2px;")
        return b

    def _section_title(self, text):
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 2, 0, 4)
        vl.setSpacing(2)
        lbl = QLabel(text)
        lbl.setFont(QFont("Consolas", self._BASE_LBL, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {ACCENT}; letter-spacing: 3px; background: transparent;")
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {ACCENT};")
        vl.addWidget(lbl)
        vl.addWidget(line)
        return w

    def _stat_block(self, caption):
        cap = QLabel(caption)
        cap.setFont(QFont("Consolas", self._BASE_LBL))
        cap.setStyleSheet(f"color: {TEXT_DIM}; letter-spacing: 2px; background: transparent;")
        val = QLabel("—")
        val.setFont(QFont("Consolas", self._BASE_STAT, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {ACCENT}; background: transparent;")
        bar = self._bar_widget()
        return cap, val, bar

    def _module_row(self, name):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 1, 0, 1)
        hl.setSpacing(6)
        dot = QLabel("◆")
        dot.setFont(QFont("Consolas", 6))
        dot.setStyleSheet(f"color: {TEXT_DIM}; background: transparent;")
        lbl = QLabel(name)
        lbl.setFont(QFont("Consolas", self._BASE_MOD, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        hl.addWidget(dot)
        hl.addWidget(lbl)
        hl.addStretch()
        return row, dot, lbl

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(2)

        layout.addWidget(self._section_title("SYSTEM"))

        self.time_lbl = QLabel("00:00")
        self.time_lbl.setFont(QFont("Consolas", self._BASE_TIME, QFont.Weight.Bold))
        self.time_lbl.setStyleSheet(f"color: {TEXT_MAIN}; background: transparent;")
        layout.addWidget(self.time_lbl)

        self.date_lbl = QLabel("--.--.----")
        self.date_lbl.setFont(QFont("Consolas", self._BASE_LBL))
        self.date_lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; padding-bottom: 4px;")
        layout.addWidget(self.date_lbl)

        layout.addWidget(self._divider())
        layout.addSpacing(2)

        cap, self.cpu_lbl, self.cpu_bar = self._stat_block("CPU")
        layout.addWidget(cap); layout.addWidget(self.cpu_lbl); layout.addWidget(self.cpu_bar)
        layout.addSpacing(6)

        cap, self.ram_lbl, self.ram_bar = self._stat_block("RAM")
        layout.addWidget(cap); layout.addWidget(self.ram_lbl); layout.addWidget(self.ram_bar)
        layout.addSpacing(6)

        self.gpu_widget = QWidget()
        self.gpu_widget.setStyleSheet("background: transparent;")
        gv = QVBoxLayout(self.gpu_widget)
        gv.setContentsMargins(0, 0, 0, 0)
        gv.setSpacing(2)
        cap, self.gpu_lbl, self.gpu_bar = self._stat_block("GPU")
        gv.addWidget(cap); gv.addWidget(self.gpu_lbl); gv.addWidget(self.gpu_bar)
        self.gpu_widget.hide()
        layout.addWidget(self.gpu_widget)

        layout.addStretch()
        layout.addWidget(self._divider())
        layout.addWidget(self._section_title("MODULES"))
        layout.addSpacing(2)

        self.mod_tts   = self._module_row("TTS")
        self.mod_voice = self._module_row("VOICE")
        self.mod_ai    = self._module_row("AI CORE")
        self.mod_wake  = self._module_row("WAKE")
        for row, _, _ in [self.mod_tts, self.mod_voice, self.mod_ai, self.mod_wake]:
            layout.addWidget(row)

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)
        self._tick_clock()

    def _tick_clock(self):
        import datetime
        n = datetime.datetime.now()
        self.time_lbl.setText(n.strftime("%H:%M"))
        self.date_lbl.setText(n.strftime("%d.%m.%Y"))

    def _start_monitor(self):
        try:
            import psutil
            self._mon = SysMonitorThread()
            self._mon.stats_ready.connect(self._on_stats)
            self._mon.start()
        except ImportError:
            self.cpu_lbl.setText("N/A")
            self.ram_lbl.setText("N/A")

    def _on_stats(self, cpu, ram, gpu):
        self.cpu_lbl.setText(f"{cpu:.0f}%")
        ram_color = RED_ACCENT if ram > 85 else (ORANGE if ram > 70 else ACCENT)
        self.ram_lbl.setStyleSheet(f"color: {ram_color}; background: transparent;")
        self.ram_lbl.setText(f"{ram:.0f}%")
        self._fill_bar(self.cpu_bar, cpu / 100)
        self._fill_bar(self.ram_bar, ram / 100)
        if gpu >= 0:
            self.gpu_lbl.setText(f"{gpu:.0f}%")
            self._fill_bar(self.gpu_bar, gpu / 100)
            self.gpu_widget.show()

    def _fill_bar(self, bar, pct):
        pct   = max(0.0, min(pct, 1.0))
        color = ACCENT if pct < 0.70 else (ORANGE if pct < 0.90 else RED_ACCENT)
        stop  = f"{pct:.2f}"
        nxt   = f"{min(pct + 0.01, 1.0):.2f}"
        bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {color},stop:{stop} {color},"
            f"stop:{nxt} {ACCENT_DIM},stop:1 {ACCENT_DIM});"
            f"border-radius: 2px;"
        )

    def set_module_status(self, name: str, active: bool):
        mapping = {
            "TTS": self.mod_tts, "VOICE": self.mod_voice,
            "AI": self.mod_ai, "WAKE": self.mod_wake
        }
        if name in mapping:
            _, dot, lbl = mapping[name]
            c = ACCENT if active else TEXT_DIM
            dot.setStyleSheet(f"color: {c}; background: transparent;")
            lbl.setStyleSheet(f"color: {c}; background: transparent; letter-spacing: 1px;")