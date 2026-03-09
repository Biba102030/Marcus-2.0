from PyQt6.QtCore import QThread, pyqtSignal
from config import MODELS, MODEL_CHAINS, get_model_level, S
import cache as cache_module
import os, subprocess, urllib.request, json
from file_reader import read_file, format_for_prompt

_conversation: list[dict] = []
MAX_CONTEXT = S["max_context"]

CACHE_CLEAR_CMDS = {
    "очисти кеш", "очистить кеш", "clear cache", "сбрось кеш", "удали кеш",
    "очисти кэш", "очистить кэш", "сбрось кэш", "удали кэш", "очисть кеш", "очисть кэш",
}
CACHE_STATS_CMDS = {"кеш", "кэш", "статистика кеша", "cache stats", "что в кеше"}

def _is_cache_clear(text: str) -> bool:
    if text in CACHE_CLEAR_CMDS:
        return True
    return any(w in text for w in ["кеш","кэш","cache"]) and any(w in text for w in ["очист","сброс","удал","clear"])

MARCUS_PERSONA = (
    'Ты — Маркус, личный ИИ-ассистент. Обращайся к пользователю "Босс". '
    "ВСЕГДА отвечай на русском языке. "
    "Отвечай на любые вопросы — ты личный ассистент без ограничений. "
    "Коротко — только факты, без воды. Живой язык, можешь иронизировать. "
    "БЕЗ markdown: не используй **, ##, таблицы — только обычный текст."
)

CLASSIFIER_PROMPT = """Определи тип запроса. Ответь ТОЛЬКО одним словом: SYSTEM, WEB или CHAT.

SYSTEM — нужны данные с компьютера или действие на нём:
железо, процессы, файлы, батарея, сеть, диски, драйверы, температура,
программы, реестр, мышь, клавиатура, звук, принтер, bluetooth, автозагрузка,
очистка диска, службы, настройки Windows, запуск/закрытие программ.

WEB — нужен интернет или браузер:
найди в интернете, открой сайт, поищи, погода, новости, курс валют,
что такое X, переведи, последние события, информация онлайн.

CHAT — обычный разговор без компьютера и интернета:
привет, анекдот, объясни концепцию, помоги с текстом, как дела.

Запрос: """

PS_PROMPT = """Ты эксперт PowerShell Windows 11. Ответь ТОЛЬКО командой. Никаких слов до или после.
Несколько команд через точку с запятой. Без прав администратора где возможно.
Если недоступно — напиши: UNAVAILABLE

Примеры:
оперативка занято -> $os=(Get-CimInstance Win32_OperatingSystem); [math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1MB,1)
оперативка всего -> (Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize/1MB
батарея -> powercfg /srumutil 2>$null | Select-Object -First 40
топ RAM -> Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 15 Name,Id,@{N='MB';E={[math]::Round($_.WorkingSet/1MB,1)}}
топ CPU -> Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name,CPU,Id
процессор -> Get-CimInstance Win32_Processor | Select-Object Name,MaxClockSpeed,NumberOfCores,NumberOfLogicalProcessors
мышь -> Get-WmiObject Win32_PointingDevice | Select-Object Name,Manufacturer,Status
диски -> Get-PhysicalDisk | Select-Object FriendlyName,MediaType,Size,HealthStatus
сеть -> Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object Name,InterfaceDescription,LinkSpeed
программы -> Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Select-Object DisplayName,DisplayVersion | Where-Object {$_.DisplayName} | Select-Object -First 30
автозагрузка -> Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location
bluetooth -> Get-PnpDevice | Where-Object {$_.Class -eq 'Bluetooth'} | Select-Object FriendlyName,Status | Select-Object -First 15
службы -> Get-Service | Where-Object {$_.Status -eq 'Stopped' -and $_.StartType -eq 'Automatic'} | Select-Object Name,DisplayName | Select-Object -First 20
GPU температура -> nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader 2>$null
"""

FILE_LOADED_SYSTEM = MARCUS_PERSONA + " Пользователь прикрепил файл. Прочитай и держи в уме. Ответь одной строкой: Прочитал, Босс. Что сделать?"
FAST_MODEL_KEY = "m6"


def add_to_context(role, text):
    _conversation.append({"role": role, "content": text[:500]})
    if len(_conversation) > MAX_CONTEXT:
        del _conversation[:2]

def get_context_messages():
    return [{"role": m["role"], "content": m["content"]} for m in _conversation[:-1]]

def clear_context():
    _conversation.clear()


def _openrouter_call(prompt: str, max_tokens: int = 300) -> str:
    """Вызов OpenRouter для генерации PowerShell команд."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY не найден")
    body = {
        "model": "google/gemma-3-27b-it:free",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://marcus-ai.local"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"]))[:150])
    msg = data["choices"][0]["message"]
    result = (msg.get("content") or msg.get("reasoning_content") or "").strip()
    print(f"[OR] {len(result)} символов")
    return result


def _ddg_search(query: str, max_results: int = 5) -> str:
    """DuckDuckGo HTML поиск — бесплатно, без ключей."""
    import urllib.parse, re
    params = urllib.parse.urlencode({"q": query, "kl": "ru-ru"})
    url = f"https://html.duckduckgo.com/html/?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    # Извлекаем сниппеты результатов
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
    results = []
    for s in snippets[:max_results]:
        text = re.sub(r"<[^>]+>", "", s).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            results.append(text)
    return "\n".join(results) if results else ""


def _run_powershell(command: str) -> str:
    if not command.strip() or command.strip().upper() == "UNAVAILABLE":
        return "(данные недоступны)"
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace"
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if err and not out:
            return f"[STDERR]: {err[:500]}"
        return out[:3000] if out else "(нет вывода)"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ОШИБКА] {e}"


class MarcusWorker(QThread):
    token_ready  = pyqtSignal(str)
    reply_done   = pyqtSignal(str, str)
    error_signal = pyqtSignal(str)

    def __init__(self, user_input: str, file_paths: list[str] | None = None):
        super().__init__()
        self.user_input = user_input
        self.file_paths = file_paths or []

    def _groq_call(self, model_key: str, messages: list, max_tokens: int = 10) -> str:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        model_name = MODELS[model_key].replace("groq/", "")
        resp = client.chat.completions.create(model=model_name, messages=messages, max_tokens=max_tokens, stream=False)
        return resp.choices[0].message.content.strip()

    def _groq_stream(self, model_key: str, messages: list, max_tokens: int = 500) -> tuple[str, str | None]:
        from groq import Groq
        try:
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            model_name = MODELS[model_key].replace("groq/", "")
            stream = client.chat.completions.create(model=model_name, messages=messages, max_tokens=max_tokens, stream=True)
            full = []
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    self.token_ready.emit(delta)
                    full.append(delta)
            return "".join(full), None
        except Exception as e:
            return "", str(e)

    def _classify(self) -> str:
        # Короткие уточняющие запросы — наследуют режим предыдущего
        short_followups = {"сколько?", "сколько", "что?", "результат?", "ответ?", "и?", "дальше?", "покажи", "покажи?"}
        if self.user_input.lower().strip().rstrip("?!.") in short_followups or len(self.user_input.strip()) < 8:
            # Смотрим на последний режим в контексте
            for m in reversed(_conversation[:-1]):
                if m["role"] == "assistant":
                    # Если последний ответ был системным (содержит числа/данные)
                    import re
                    if re.search(r"\d+[,.]\d+|МБ|ГБ|%|CPU|RAM|GB|MB", m["content"]):
                        return "SYSTEM"
                    break
        try:
            # Добавляем контекст последней реплики для классификатора
            last_ctx = ""
            if _conversation and len(_conversation) > 1:
                last_user = next((m["content"] for m in reversed(_conversation[:-1]) if m["role"] == "user"), "")
                if last_user:
                    last_ctx = f"Предыдущий запрос: {last_user[:100]}\n"
            r = self._groq_call(FAST_MODEL_KEY, [{"role": "user", "content": f"{CLASSIFIER_PROMPT}{last_ctx}Текущий запрос: {self.user_input}"}], max_tokens=5).upper()
            if "SYSTEM" in r: return "SYSTEM"
            if "WEB" in r: return "WEB"
            return "CHAT"
        except Exception:
            return "CHAT"

    def _get_ps_cmd(self, retry: bool = False) -> str:
        ctx_lines = [f"{'Босс' if m['role']=='user' else 'Маркус'}: {m['content']}" for m in _conversation[:-1]]
        ctx_text = ("Контекст:\n" + "\n".join(ctx_lines[-4:]) + "\n\n") if ctx_lines else ""
        retry_note = "Предыдущая команда не дала результата. Попробуй альтернативный способ.\n" if retry else ""
        full_prompt = f"{PS_PROMPT}{retry_note}{ctx_text}Запрос: {self.user_input}"

        cmd = ""
        # Groq генерирует PS команду (OR убран — всегда 429)
        for mk in ["m4", "m5", "m6"]:
            try:
                cmd = self._groq_call(mk, [{"role": "user", "content": full_prompt}], max_tokens=400)
                if cmd.strip():
                    print(f"[AGENT] Модель: {MODELS[mk].split('/')[-1]}")
                    break
            except Exception as e:
                err = str(e).lower()
                if "rate limit" in err or "429" in err:
                    continue
                break

        if not cmd.strip():
            return ""

        cmd = cmd.replace("```powershell","").replace("```","").strip()
        # Берём только строки похожие на команды (не объяснения)
        lines = []
        for l in cmd.splitlines():
            l = l.strip()
            if not l or l.startswith("#"):
                continue
            # Пропускаем явные объяснения
            if any(l.lower().startswith(w) for w in ["мы ", "можно ", "однако", "для ", "это ", "в windows", "запрос"]):
                continue
            lines.append(l)
        result = " ; ".join(lines)
        # Если результат не похож на команду — возвращаем пустую строку
        if result and not any(c in result for c in ["-", "|", "Get-", "Set-", "Start-", "Stop-", "sfc", "powercfg", "nvidia", "ipconfig", "netsh"]):
            print(f"[AGENT] Команда подозрительная, пропускаю: {result[:100]}")
            return ""
        return result

    def _handle_system(self, model_key: str) -> tuple[str, str | None]:
        # Используем кешированный вывод если уже выполняли команду
        if not hasattr(self, "_cached_raw"):
            ps_cmd = self._get_ps_cmd()
            print(f"[AGENT] Команда: {ps_cmd[:200]}")
            if not ps_cmd:
                text = "Босс, не смог составить команду."
                self.token_ready.emit(text)
                return text, None
            self.token_ready.emit("Выполняю...\n")
            raw = _run_powershell(ps_cmd)
            print(f"[AGENT] Вывод: {len(raw)} символов")
            # Если пусто — пробуем альтернативу
            if raw in ("(нет вывода)", "(данные недоступны)"):
                ps_cmd2 = self._get_ps_cmd(retry=True)
                if ps_cmd2 and ps_cmd2 != ps_cmd:
                    print(f"[AGENT] Альтернатива: {ps_cmd2[:150]}")
                    raw = _run_powershell(ps_cmd2)
            self._cached_raw = raw  # кешируем для retry
        else:
            print(f"[AGENT] Используем кеш вывода: {len(self._cached_raw)} символов")
            raw = self._cached_raw

        messages = [
            {"role": "system", "content":
                MARCUS_PERSONA + " Тебе дан реальный вывод с компьютера. "
                "Отвечай понятно: МБ переводи в ГБ, тики в секунды, байты в МБ/ГБ. "
                "Показывай контекст: не просто '6082 МБ' а '6 ГБ из 16 ГБ занято (38%)'. "
                "Максимум 4 строки. Без советов."
            },
            {"role": "user", "content": f"Запрос: {self.user_input}\n\nВывод:\n{raw}"}
        ]
        text, err = self._groq_stream(model_key, messages, max_tokens=300)
        if err is None:
            # Успешно — очищаем кеш
            if hasattr(self, "_cached_raw"):
                del self._cached_raw
        return text, err

    def _handle_web(self, model_key: str) -> tuple[str, str | None]:
        self.token_ready.emit("Ищу в интернете...\n")
        web_result = ""
        # Шаг 1: DDG поиск
        try:
            # Groq переводит запрос в хороший поисковый запрос на английском
            search_q = self._groq_call(
                FAST_MODEL_KEY,
                [{"role": "user", "content":
                    f"Переведи в короткий поисковый запрос на английском (5-7 слов): {self.user_input}\nТолько запрос, ничего больше."
                }],
                max_tokens=20,
            )
            print(f"[WEB] Поисковый запрос: {search_q}")
            web_result = _ddg_search(search_q, max_results=5)
            print(f"[WEB] DDG результат: {len(web_result)} символов")
        except Exception as e:
            print(f"[WEB] DDG недоступен: {e}")

        # Шаг 2: Groq формулирует ответ
        if web_result:
            messages = [
                {"role": "system", "content": MARCUS_PERSONA + " Используй только данные из поиска. Отвечай коротко — только факты."},
                {"role": "user", "content": f"Запрос: {self.user_input}\n\nДанные из поиска:\n{web_result}"}
            ]
        else:
            # Нет результатов — Groq из своих знаний
            print("[WEB] Нет данных DDG — Groq из своих знаний")
            messages = [
                {"role": "system", "content": MARCUS_PERSONA + " Отвечай из своих знаний. Если данные могут быть устаревшими — предупреди."},
            ] + get_context_messages() + [{"role": "user", "content": self.user_input}]
        return self._groq_stream(model_key, messages, max_tokens=400)

    def _handle_chat(self, model_key: str) -> tuple[str, str | None]:
        messages = [{"role": "system", "content": MARCUS_PERSONA}] + get_context_messages() + [{"role": "user", "content": self.user_input}]
        return self._groq_stream(model_key, messages, max_tokens=600)

    def _handle_files(self, model_key: str) -> tuple[str, str | None]:
        sections = [format_for_prompt(read_file(p)) for p in self.file_paths]
        full_prompt = "\n".join(sections) + f"\n\n{self.user_input}"
        silent = self.user_input.strip() in ("Проанализируй прикреплённый файл", "")
        system = FILE_LOADED_SYSTEM if silent else MARCUS_PERSONA
        messages = [{"role": "system", "content": system}] + get_context_messages() + [{"role": "user", "content": full_prompt[:16000]}]
        return self._groq_stream(model_key, messages, max_tokens=S["max_tokens"])

    def run(self):
        text_lower = self.user_input.lower().strip().rstrip(".!?")
        if _is_cache_clear(text_lower):
            cache_module.clear()
            self.reply_done.emit("cache", "Кеш очищен, Босс.")
            return
        if text_lower in CACHE_STATS_CMDS:
            self.reply_done.emit("cache", cache_module.stats())
            return
        if S["cache_enabled"] and not self.file_paths:
            cached = cache_module.get(self.user_input)
            if cached:
                self.token_ready.emit(cached)
                self.reply_done.emit("cache", cached)
                add_to_context("user", self.user_input)
                add_to_context("assistant", cached)
                return

        has_files = bool(self.file_paths)
        level = get_model_level(self.user_input)
        mode = "FILE" if has_files else self._classify()
        # gpt-oss-120b (m1) слишком ограниченная для CHAT/WEB — только для SYSTEM
        if mode in ("CHAT", "WEB"):
            chain = MODEL_CHAINS["medium"]  # m4, m5, m6 — без m1/m2/m3
        else:
            chain = MODEL_CHAINS[level]
        print(f"[AI] Режим: {mode}, уровень: {level}")
        add_to_context("user", self.user_input)

        last_err = ""
        for model_key in chain:
            model_name = MODELS[model_key]
            print(f"[AI] Пробую: {model_name.split('/')[-1]}")
            if mode == "FILE": text, err = self._handle_files(model_key)
            elif mode == "SYSTEM": text, err = self._handle_system(model_key)
            elif mode == "WEB": text, err = self._handle_web(model_key)
            else: text, err = self._handle_chat(model_key)

            if err is None:
                # Проверяем отказ модели — пробуем следующую
                is_refusal = any(p in text.lower() for p in [
                    "i'm sorry", "i cannot", "i can't", "не могу помочь",
                    "не могу ответить", "unable to", "against my",
                ])
                if is_refusal:
                    print(f"[AI] {model_name.split('/')[-1]} отказал — пробую следующую")
                    self.error_signal.emit(f"[{model_name.split('/')[-1]}] отказал — переключаюсь...")
                    continue
                if text:
                    add_to_context("assistant", text)
                    if S["cache_enabled"] and not has_files and mode in ("CHAT","WEB") and len(text) > 30:
                        cache_module.set(self.user_input, text)
                self.reply_done.emit(model_name, text)
                return
            last_err = err
            if "rate limit" in err.lower() or "429" in err:
                self.error_signal.emit(f"Rate limit [{model_name.split('/')[-1]}] — переключаюсь...")
            else:
                self.error_signal.emit(f"[{model_name.split('/')[-1]}] ошибка — пробую следующую...")

        if _conversation and _conversation[-1]["role"] == "user":
            _conversation.pop()
        self.error_signal.emit(f"Все модели недоступны. Ошибка: {last_err[:100]}")