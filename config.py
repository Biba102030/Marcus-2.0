import os
import json
from dotenv import load_dotenv

load_dotenv()

# ── Настройки из settings.json ────────────────────────────────────────────────
_SETTINGS_PATH = r"C:\Marcus\settings.json"

def load_settings() -> dict:
    defaults = {
        "voice": "ru-RU-DmitryNeural", "speed_factor": 1.1,
        "wake_words": ["маркус", "marcus", "эй маркус", "hey marcus"],
        "wake_volume_min": 0.008, "wake_chunk_secs": 2.0,
        "silence_threshold": 0.015, "silence_secs": 3.0,
        "max_context": 6, "max_tokens": 8192,
        "tts_min_chunk_len": 30, "cache_enabled": True,
    }
    if os.path.exists(_SETTINGS_PATH):
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
            print(f"[CONFIG] Настройки загружены из {_SETTINGS_PATH}")
        except Exception as e:
            print(f"[CONFIG] Ошибка settings.json: {e}")
    return defaults

S = load_settings()

# ── Модели Groq ───────────────────────────────────────────────────────────────
MODELS = {
    "m1": "groq/openai/gpt-oss-120b",
    "m2": "groq/moonshotai/kimi-k2-instruct",
    "m3": "groq/meta-llama/llama-4-maverick-17b-128e-instruct",
    "m4": "groq/openai/gpt-oss-20b",
    "m5": "groq/llama-3.3-70b-versatile",
    "m6": "groq/meta-llama/llama-4-scout-17b-16e-instruct",
}

FULL_CHAIN   = ["m1", "m2", "m3", "m4", "m5", "m6"]
MODEL_CHAINS = {
    "strong": FULL_CHAIN,
    "medium": FULL_CHAIN[3:],  # m4, m5, m6
}

# ── Пути ──────────────────────────────────────────────────────────────────────
MEMORY_DIR  = r"C:\Marcus\Memory"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
MARCUS_DIR  = r"C:\Marcus"

# ── Инициализация папок ───────────────────────────────────────────────────────
os.makedirs(MEMORY_DIR, exist_ok=True)
os.makedirs(os.path.join(MEMORY_DIR, "important"), exist_ok=True)
os.makedirs(os.path.join(MEMORY_DIR, "temp"), exist_ok=True)


def get_model_level(text: str) -> str:
    t = text.lower()
    if any(k in t for k in [
        "код", "напиши", "функция", "класс", "дебаг", "sql", "парс",
        "скрипт", "файл", "папка", "браузер", "html", "измени",
        "ram", "cpu", "оптимиз", "очисти", "сканир",
    ]):
        return "strong"
    return "medium"