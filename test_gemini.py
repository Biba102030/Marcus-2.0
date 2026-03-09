"""Запусти: python test_gemini.py"""
import os, urllib.request, json
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("OPENROUTER_API_KEY")

MODELS = [
    "deepseek/deepseek-chat-v3-0324:free",
    "deepseek/deepseek-r1-0528:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "google/gemma-3-27b-it:free",
]

for model in MODELS:
    try:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "Ответь одним словом: работаю"}],
            "max_tokens": 20,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            print(f"✗ {model}: {data['error'].get('message','?')[:80]}")
        else:
            answer = (data["choices"][0]["message"].get("content") or "").strip()
            print(f"✓ {model}: {answer}")
    except Exception as e:
        print(f"✗ {model}: {str(e)[:80]}")