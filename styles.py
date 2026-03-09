# Все цвета и CSS
BG_DEEP    = "#050A0F"
BG_PANEL   = "#0A1520"
BG_SIDE    = "#070F1A"
BG_INPUT   = "#0D1B2A"
ACCENT     = "#00FFD1"
ACCENT2    = "#0088FF"
ACCENT_DIM = "#005544"
TEXT_MAIN  = "#C8F0E8"
TEXT_DIM   = "#3A6655"
MSG_USER   = "#0D2235"
MSG_BOT    = "#071A10"
RED_ACCENT = "#FF4444"
ORANGE     = "#FF9900"

# Два шрифта:
# FONT_MONO  — интерфейс, кнопки, метки, панель (терминальный стиль)
# FONT_TEXT  — текст сообщений чата (читаемый, не моноширинный)
FONT_MONO = "'Consolas', 'Cascadia Code', monospace"
FONT_TEXT = "'Segoe UI', 'Arial', sans-serif"

STYLE_MAIN = f"""
QMainWindow, QWidget#root {{ background-color: {BG_DEEP}; }}
QScrollArea {{ background-color: transparent; border: none; }}
QScrollBar:vertical {{ background: {BG_PANEL}; width: 5px; border-radius: 3px; }}
QScrollBar::handle:vertical {{ background: {ACCENT_DIM}; border-radius: 3px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""

STYLE_INPUT = f"""
QLineEdit {{
    background-color: {BG_INPUT}; color: {ACCENT};
    border: 1px solid {ACCENT_DIM}; border-radius: 10px;
    padding: 10px 16px; font-size: 13px;
    font-family: {FONT_MONO}; letter-spacing: 0.3px;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; background-color: #0F2030; }}
"""

def btn_style(bg, fg, border, hover_bg=None, hover_fg=None):
    hbg = hover_bg or ACCENT
    hfg = hover_fg or BG_DEEP
    return f"""
QPushButton {{
    background-color: {bg}; color: {fg};
    border: 1px solid {border}; border-radius: 10px;
    padding: 0px 16px; font-size: 12px;
    font-family: {FONT_MONO}; font-weight: bold; letter-spacing: 1px;
}}
QPushButton:hover {{ background-color: {hbg}; color: {hfg}; border-color: {hbg}; }}
QPushButton:pressed {{ background-color: #00AA88; }}
QPushButton:disabled {{ background-color: #071510; color: {TEXT_DIM}; border-color: {TEXT_DIM}; }}
"""

STYLE_SEND     = btn_style(ACCENT_DIM, ACCENT, ACCENT)
STYLE_MIC_IDLE = btn_style("#1A0A0A", "#FF6666", "#AA2222", "#2A1010", RED_ACCENT)
STYLE_MIC_REC  = btn_style(RED_ACCENT, "#FFFFFF", "#FF8888", "#CC2222", "#FFFFFF")
STYLE_TTS_ON   = btn_style(ACCENT_DIM, ACCENT, ACCENT)
STYLE_TTS_OFF  = btn_style("#1A1A0A", "#888866", "#555533")

def mode_btn_style(active: bool) -> str:
    if active:
        return f"""QPushButton {{
            background-color: {ACCENT_DIM}; color: {ACCENT};
            border: 1px solid {ACCENT}; border-radius: 8px;
            padding: 5px 16px; font-size: 11px;
            font-family: {FONT_MONO}; font-weight: bold; letter-spacing: 1.5px;
        }}"""
    return f"""QPushButton {{
        background-color: transparent; color: {TEXT_DIM};
        border: 1px solid {TEXT_DIM}; border-radius: 8px;
        padding: 5px 16px; font-size: 11px;
        font-family: {FONT_MONO}; letter-spacing: 1.5px;
    }}
    QPushButton:hover {{ color: {TEXT_MAIN}; border-color: {TEXT_MAIN}; }}"""