"""Тест какие модели OpenRouter поддерживают web search бесплатно"""
import os, urllib.request, json
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("OPENROUTER_API_KEY")

# Модели которые могут иметь web search
MODELS = [
    "google/gemma-3-27b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "perplexity/sonar",           # платный но дешёвый — поиск встроен
    "perplexity/sonar-pro",
]

print("Тест web search через OpenRouter...\n")
for model in MODELS:
    try:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Какой сейчас курс доллара к рублю? Дай точную цифру."}],
            "max_tokens": 50,
            "plugins": [{"id": "web"}],
        }
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            print(f"✗ {model}: {data['error'].get('message','?')[:80]}")
        else:
            answer = (data["choices"][0]["message"].get("content") or "").strip()[:100]
            print(f"✓ {model}: {answer}")
    except Exception as e:
        print(f"✗ {model}: {str(e)[:80]}")