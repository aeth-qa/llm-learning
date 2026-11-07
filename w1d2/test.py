import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from openai import OpenAI

# ─── 1. Конфиг ──────────────────────────────────────────────────────────────
key_file = Path(__file__).parent.parent / "key.deepseek"
API_KEY = key_file.read_text(encoding="utf-8").strip()

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

MODEL = "deepseek-chat"
RUNS_PER_VARIANT = 5
OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)

# ─── 2. Базовый запрос и хелперы ────────────────────────────────────────────
BASE_QUESTION = "Назови 3 страны, их столицы и население столиц."
SYSTEM_DEFAULT = "Ты — полезный ассистент."

def make_messages(user_text, system=SYSTEM_DEFAULT):
    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_text},
    ]

# ─── 3. Отправка запроса ────────────────────────────────────────────────────
def ask(messages, **params):
    try:
        response = client.chat.completions.create(
            model=MODEL, messages=messages, **params,
        )
        choice = response.choices[0]
        return {
            "ok": True,
            "content": choice.message.content,
            "finish_reason": choice.finish_reason,
            "usage": {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens,
                "total": response.usage.total_tokens,
            },
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "finish_reason": "error",
        }

# ─── 4. Валидаторы ──────────────────────────────────────────────────────────
# Теперь валидаторы принимают весь result (словарь), чтобы видеть и ошибки API.

def validate_not_empty(result):
    if not result["ok"]:
        return (False, result["error"])
    if not result["content"] or not result["content"].strip():
        return (False, "empty content")
    return (True, None)

def validate_pipe_format(result):
    if not result["ok"]:
        return (False, result["error"])
    content = result["content"]
    if not content:
        return (False, "empty content")
    
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if len(lines) != 3:
        return (False, f"expected 3 non-empty lines, got {len(lines)}")
        
    pat = re.compile(
        r"^Country:\s*(.+?)\s*\|\s*Capital:\s*(.+?)\s*\|\s*Population:\s*(.+?)\s*$"
    )
    for i, ln in enumerate(lines, 1):
        m = pat.match(ln)
        if not m:
            return (False, f"line {i} doesn't match pipe format: {ln[:60]!r}")
        
        # Достаем население и проверяем, что это число (после удаления пробелов)
        pop_str = m.group(3)
        clean_pop = pop_str.replace(" ", "").replace(",", "") # удаляем пробелы и запятые
        if not clean_pop.isdigit():
            return (False, f"line {i}: Population '{pop_str}' is not a valid number")
            
    return (True, None)

def validate_no_stop_marker(result):
    if not result["ok"]:
        return (False, result["error"])
    if "===END===" in result["content"]:
        return (False, "stop marker leaked into content")
    return (True, None)

def validate_json_schema(result):
    if not result["ok"]:
        return (False, result["error"])
    content = result["content"]
    if not content:
        return (False, "empty content")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return (False, f"JSONDecodeError: {e}")
    if not isinstance(data, dict):
        return (False, f"top-level is {type(data).__name__}, expected object")
    if "countries" not in data:
        return (False, f"missing 'countries', keys={list(data.keys())}")
    countries = data["countries"]
    if not isinstance(countries, list):
        return (False, f"'countries' is {type(countries).__name__}, expected array")
    if len(countries) != 3:
        return (False, f"expected 3 countries, got {len(countries)}")
    for i, c in enumerate(countries, 1):
        if not isinstance(c, dict):
            return (False, f"country #{i} is not an object")
        for field, ftype in [("country", str),
                             ("capital", str),
                             ("population", int)]:
            if field not in c:
                return (False, f"country #{i} missing '{field}'")
            if not isinstance(c[field], ftype):
                return (False, f"country #{i} '{field}' is "
                               f"{type(c[field]).__name__}, expected {ftype.__name__}")
    return (True, None)

def validate_expected_error(result):
    """Критерий успеха для 07: мы ОЖИДАЕМ ошибку 400 с конкретным текстом."""
    if result["ok"]:
        return (False, "expected error, but got success")
    if "This response_format type is unavailable now" not in result["error"]:
        return (False, f"wrong error message: {result['error'][:80]}")
    return (True, None)

def validate_stop_effect(res_base, res_stop):
    """Критерий успеха для 05: сравниваем прогон без stop и со stop."""
    if not res_base["ok"]:
        return (False, f"baseline error: {res_base['error'][:60]}")
    if not res_stop["ok"]:
        return (False, f"stop error: {res_stop['error'][:60]}")
    
    # 1. Маркер должен быть в базовом (иначе модель сама его не пишет, и тест не валиден)
    if "===END===" not in res_base["content"]:
        return (False, "baseline missing marker ===END===")
    
    # 2. Маркер не должен протечь в stop-ответ (значит, API его вырезал)
    if "===END===" in res_stop["content"]:
        return (False, "stop leaked ===END=== into content")
    
    # 3. (Опционально) Если хотим убедиться, что API обрезал именно по маркеру,
    # можно проверить, что stop-ответ является префиксом базового (работает только при temp=0)
    # Но для temp=1.0 мы просто верим, что раз маркер есть в базовом и нет в стоповом — стоп сработал.
    
    return (True, None)

# ─── 5. Запись обменов в файл ───────────────────────────────────────────────
def format_params(params):
    keys = ["temperature", "max_tokens", "stop", "response_format"]
    parts = []
    for k in keys:
        v = params.get(k)
        if k == "response_format" and v:
            v = v.get("type", v)
        parts.append(f"{k}={v!r}")
    return "  ".join(parts)

def format_messages(messages):
    lines = []
    for m in messages:
        content = m["content"].replace("\n", "\n         ")
        lines.append(f"    {m['role']}: «{content}»")
    return "\n".join(lines)

def log_exchange(f, run_num, messages, params, result, valid_ok, valid_err):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"=== Обмен #{run_num}  ({ts}) ===\n")
    f.write(f"[REQUEST]\n  model={MODEL}  {format_params(params)}\n")
    f.write(f"  messages:\n{format_messages(messages)}\n\n")
    
    if result["ok"]:
        f.write(f"[RESPONSE]\n")
        f.write(f"  finish_reason: {result['finish_reason']}\n")
        f.write(f"  usage: prompt={result['usage']['prompt']}, "
                f"completion={result['usage']['completion']}, "
                f"total={result['usage']['total']}\n")
        f.write(f"  valid_ok: {valid_ok}")
        if not valid_ok:
            f.write(f"  ({valid_err})")
        f.write("\n  content:\n")
        f.write("    <<<\n")
        f.write("    " + result["content"].replace("\n", "\n    ") + "\n")
        f.write("    >>>\n")
    else:
        f.write(f"[ERROR]\n  {result['error']}\n")
        f.write(f"  valid_ok: {valid_ok}")
        if not valid_ok:
            f.write(f"  ({valid_err})")
        f.write("\n")
    f.write("\n\n")

def log_exchange_pair(f, run_num, messages, params_base, res_base, params_stop, res_stop, valid_ok, valid_err):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"=== Обмен (ПАРА) #{run_num}  ({ts}) ===\n")
    
    f.write(f"[BASELINE REQUEST]\n  model={MODEL}  {format_params(params_base)}\n")
    f.write(f"  messages:\n{format_messages(messages)}\n\n")
    if res_base["ok"]:
        f.write(f"[BASELINE RESPONSE]\n  finish_reason: {res_base['finish_reason']}\n")
        f.write(f"  usage: prompt={res_base['usage']['prompt']}, completion={res_base['usage']['completion']}, total={res_base['usage']['total']}\n")
        f.write("  content:\n    <<<\n    " + res_base["content"].replace("\n", "\n    ") + "\n    >>>\n")
    else:
        f.write(f"[BASELINE ERROR]\n  {res_base['error']}\n")
    f.write("\n")

    f.write(f"[STOP REQUEST]\n  model={MODEL}  {format_params(params_stop)}\n")
    f.write(f"  messages:\n{format_messages(messages)}\n\n")
    if res_stop["ok"]:
        f.write(f"[STOP RESPONSE]\n  finish_reason: {res_stop['finish_reason']}\n")
        f.write(f"  usage: prompt={res_stop['usage']['prompt']}, completion={res_stop['usage']['completion']}, total={res_stop['usage']['total']}\n")
        f.write("  content:\n    <<<\n    " + res_stop["content"].replace("\n", "\n    ") + "\n    >>>\n")
    else:
        f.write(f"[STOP ERROR]\n  {res_stop['error']}\n")
        
    f.write(f"\n[COMPARE]\n  valid_ok: {valid_ok}")
    if not valid_ok:
        f.write(f"  ({valid_err})")
    f.write("\n\n")

# ─── 6. Прогон одного варианта ──────────────────────────────────────────────
def run_variant(variant):
    path = OUT_DIR / f"{variant['name']}.txt"
    valid_results = []
    fail_reasons = []
    finish_reasons = []

    with open(path, "w", encoding="utf-8") as f:
        for i in range(1, RUNS_PER_VARIANT + 1):
            # Ветка для парного прогона (вариант 05)
            if "validator_with_baseline" in variant:
                base_params = variant["baseline_params"]
                res_base = ask(variant["messages"], **base_params)
                res_stop = ask(variant["messages"], **variant["params"])
                valid_ok, valid_err = variant["validator_with_baseline"](res_base, res_stop)
                log_exchange_pair(f, i, variant["messages"], base_params, res_base, variant["params"], res_stop, valid_ok, valid_err)
                finish_reasons.append(res_stop["finish_reason"])
            else:
                # Обычный прогон
                result = ask(variant["messages"], **variant["params"])
                valid_ok, valid_err = variant["validator"](result)
                
                # Проверка expected_finish_reason (для 03 и 07)
                if valid_ok and "expected_finish_reason" in variant:
                    expected = variant["expected_finish_reason"]
                    actual = result.get("finish_reason")
                    if actual != expected:
                        valid_ok = False
                        valid_err = f"expected finish_reason={expected}, got {actual}"
                
                log_exchange(f, i, variant["messages"], variant["params"], result, valid_ok, valid_err)
                finish_reasons.append(result["finish_reason"])

            valid_results.append(valid_ok)
            if not valid_ok:
                fail_reasons.append(valid_err)

    return {
        "name": variant["name"],
        "runs": RUNS_PER_VARIANT,
        "valid_ok": sum(valid_results),
        "finish_reasons": finish_reasons,
        "first_fail": fail_reasons[0] if fail_reasons else "",
    }

# ─── 7. Сводная таблица ─────────────────────────────────────────────────────
def write_summary(stats):
    path = OUT_DIR / "summary.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Сводка ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
        f.write(f"# model={MODEL}, runs={RUNS_PER_VARIANT}\n\n")
        header = f"{'variant':<22} {'runs':>4} {'valid_ok':>9}  {'finish_reasons':<22} first_fail"
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")
        for s in stats:
            fr = Counter(s["finish_reasons"])
            fr_str = ", ".join(f"{k}×{v}" for k, v in fr.items())
            ff = s["first_fail"][:60] if s["first_fail"] else ""
            f.write(f"{s['name']:<22} {s['runs']:>4} "
                    f"{s['valid_ok']:>4}/{s['runs']:<4}  "
                    f"{fr_str:<22} {ff}\n")

# ─── 8. Варианты ────────────────────────────────────────────────────────────
JSON_SCHEMA = {
    "name": "countries_schema",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "countries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "country":    {"type": "string"},
                        "capital":    {"type": "string"},
                        "population": {"type": "integer"},
                    },
                    "required": ["country", "capital", "population"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["countries"],
        "additionalProperties": False,
    },
}

VARIANTS = [
    {
        "name": "01_baseline",
        "messages": make_messages(BASE_QUESTION),
        "params": {"temperature": 1.0},
        "validator": validate_not_empty,
    },
    {
        "name": "02_format_hint",
        "messages": make_messages(
            BASE_QUESTION + "\n\nОтветь строго тремя строками в формате:\n"
            "Country: <название> | Capital: <столица> | Population: <число>\n"
            "Без преамбулы, без пояснений."
        ),
        "params": {"temperature": 1.0},
        "validator": validate_pipe_format,
    },
    {
        "name": "03_max_tokens_30",
        "messages": make_messages(BASE_QUESTION),
        "params": {"temperature": 1.0, "max_tokens": 30},
        "validator": validate_not_empty,
        "expected_finish_reason": "length",  # <-- Новое: ожидаем обрыв
    },
    {
        "name": "04_max_tokens_200",
        "messages": make_messages(BASE_QUESTION),
        "params": {"temperature": 1.0, "max_tokens": 200},
        "validator": validate_not_empty,
    },
    {
        "name": "05_stop_seq",
        "messages": make_messages(
            BASE_QUESTION + "\n\nВ конце ответа напиши ===END==="
        ),
        "params": {"temperature": 1.0, "stop": ["===END==="]},
        "baseline_params": {"temperature": 1.0}, # <-- Новое: параметры для прогона без stop
        "validator_with_baseline": validate_stop_effect, # <-- Новое: валидатор-сравнение
    },
    {
        "name": "06_json_object",
        "messages": make_messages(
            BASE_QUESTION + "\n\nВерни json вида: "
            '{"countries": [{"country": "...", "capital": "...", "population": 123}]}',
            system="Ты — полезный ассистент. Отвечай в формате json.",
        ),
        "params": {"temperature": 1.0,
                   "response_format": {"type": "json_object"}},
        "validator": validate_json_schema,
    },
    {
        "name": "07_json_schema",
        "messages": make_messages(BASE_QUESTION),
        "params": {"temperature": 1.0,
                   "response_format": {"type": "json_schema",
                                       "json_schema": JSON_SCHEMA}},
        "validator": validate_expected_error, # <-- Новое: ждем ошибку
        "expected_finish_reason": "error",    # <-- Новое: ожидаем error
    },
]

# ─── 9. Точка входа ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Запуск: {len(VARIANTS)} вариантов × {RUNS_PER_VARIANT} прогонов\n")
    all_stats = []
    for v in VARIANTS:
        print(f"  → {v['name']} ...", end=" ", flush=True)
        stats = run_variant(v)
        all_stats.append(stats)
        print(f"valid_ok {stats['valid_ok']}/{stats['runs']}")
    write_summary(all_stats)
    print(f"\nГотово. Результаты в {OUT_DIR}")