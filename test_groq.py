"""Запусти: python test_groq.py"""
import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODELS = [
    "openai/gpt-oss-20b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "qwen-qwq-32b",
    "moonshotai/kimi-k2-instruct",
]

print("Проверяю модели Groq...\n")
for model in MODELS:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "1+1=?"}],
            max_tokens=5,
        )
        answer = resp.choices[0].message.content.strip()
        # Показываем лимиты из заголовков если доступны
        print(f"✓ {model.split('/')[-1]}: {answer}")
        if hasattr(resp, 'x_groq'):
            info = resp.x_groq
            print(f"  Лимит: {info}")
    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate" in msg.lower():
            # Извлекаем время ожидания если есть
            import re
            wait = re.search(r'try again in (\S+)', msg)
            wait_str = f" — подожди {wait.group(1)}" if wait else ""
            print(f"✗ {model.split('/')[-1]}: Rate limit{wait_str}")
        elif "404" in msg or "not found" in msg.lower():
            print(f"✗ {model.split('/')[-1]}: Модель не найдена")
        else:
            print(f"✗ {model.split('/')[-1]}: {msg[:80]}")