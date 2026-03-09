import os
import sys
import threading
import ctypes
import ctypes.wintypes

# UTF-8 для консоли Windows — предотвращает крашы на unicode символах
os.environ["PYTHONUTF8"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import QObject, pyqtSignal

from window import MarcusWindow
from styles import BG_DEEP, BG_INPUT, BG_PANEL, TEXT_MAIN, ACCENT, ACCENT_DIM

MOD_CONTROL = 0x0002
MOD_SHIFT   = 0x0004
VK_M        = 0x4D
HOTKEY_ID   = 1
WM_HOTKEY   = 0x0312


class HotkeySignal(QObject):
    triggered = pyqtSignal()


def _register_hotkey(signal: HotkeySignal, stop_event: threading.Event):
    user32 = ctypes.windll.user32

    ok = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_M)
    if ok:
        print("[HOTKEY] Ctrl+Shift+M зарегистрирован — показать/скрыть Маркуса")
    else:
        print("[HOTKEY] Не удалось зарегистрировать Ctrl+Shift+M")
        return

    msg = ctypes.wintypes.MSG()
    while not stop_event.is_set():
        # PeekMessage вместо GetMessage — не блокирует навсегда,
        # не ловит WM_QUIT от системы
        has_msg = user32.PeekMessageW(
            ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY,
            0x0001  # PM_REMOVE
        )
        if has_msg:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                signal.triggered.emit()
        else:
            # Нет сообщений — спим чтобы не жрать CPU
            stop_event.wait(timeout=0.05)

    user32.UnregisterHotKey(None, HOTKEY_ID)
    print("[HOTKEY] Хоткей снят")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(BG_DEEP))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_MAIN))
    palette.setColor(QPalette.ColorRole.Base,            QColor(BG_INPUT))
    palette.setColor(QPalette.ColorRole.Text,            QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.Button,          QColor(BG_PANEL))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT_DIM))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(QColor(BG_DEEP)))
    app.setPalette(palette)

    window = MarcusWindow()
    window.show()

    def _qt_toggle():
        if window.isVisible() and not window.isMinimized():
            window.hide()
        else:
            window.show()
            window.raise_()
            window.activateWindow()

    _hotkey_signal = HotkeySignal()
    _hotkey_signal.triggered.connect(_qt_toggle)

    _stop_event = threading.Event()
    hotkey_thread = threading.Thread(
        target=_register_hotkey,
        args=(_hotkey_signal, _stop_event),
        daemon=True
    )
    hotkey_thread.start()

    # При закрытии приложения — останавливаем поток хоткея
    app.aboutToQuit.connect(_stop_event.set)

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        _stop_event.set()


if __name__ == "__main__":
    main()