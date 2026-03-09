# Кеш ответов LLM — hash(запрос) → ответ
# Хранится в C:\Marcus\Memory\cache.json
# Чистится командой "очисти кеш" или вручную

import os
import json
import hashlib
import time

CACHE_PATH = r"C:\Marcus\Memory\cache.json"


def _load() -> dict:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _key(text: str) -> str:
    """SHA256 от нормализованного запроса."""
    normalized = text.lower().strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def get(text: str) -> str | None:
    """Вернуть кешированный ответ или None если нет."""
    data = _load()
    entry = data.get(_key(text))
    if entry:
        print(f"[CACHE] Хит: {text[:50]}...")
        return entry["answer"]
    return None


def set(text: str, answer: str):
    """Сохранить ответ в кеш."""
    if len(answer) < 20:
        return  # Не кешируем короткие/пустые ответы
    data = _load()
    data[_key(text)] = {
        "question": text[:200],
        "answer":   answer,
        "ts":       time.strftime("%Y-%m-%d %H:%M")
    }
    _save(data)
    print(f"[CACHE] Сохранено: {text[:50]}...")


def clear():
    """Полностью очистить кеш."""
    if os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)
    print("[CACHE] Кеш очищен")


def stats() -> str:
    """Статистика кеша."""
    data = _load()
    if not data:
        return "Кеш пуст."
    size = os.path.getsize(CACHE_PATH) / 1024
    return f"Записей: {len(data)}, размер: {size:.1f} КБ"