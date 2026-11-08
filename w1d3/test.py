import time
import re
from datetime import datetime
from openai import OpenAI
from pathlib import Path
from collections import defaultdict

# ─── Конфиг ─────────────────────────────────────────────────────────────────
key_file = Path(__file__).parent.parent / "key.deepseek"
API_KEY = key_file.read_text(encoding="utf-8").strip()
client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)

# ─── Задачи ─────────────────────────────────────────────────────────────────
TASKS = [
    {
        "id": "sheep",
        "type": "numeric",
        "question": "У фермера было 17 овец. Все, кроме 9, убежали. "
                    "Сколько овец осталось у фермера?",
        "expected": 9,
    },
    {
        "id": "snail",
        "type": "numeric",
        "question": "Улитка ползет по столбу высотой 10 метров. За день она "
                    "поднимается на 3 метра, а за ночь сползает на 2 метра. "
                    "За сколько дней улитка доберется до вершины?",
        "expected": 8,
    },
    {
        "id": "lily",
        "type": "numeric",
        "question": "Кувшинки в пруду удваивают свою площадь каждый день. "
                    "Если они полностью покрывают пруд за 48 дней, за сколько "
                    "дней они покроют ровно половину пруда?",
        "expected": 47,
    },
    {
        "id": "clock",
        "type": "numeric",
        "question": "Сколько раз в сутки часовая и минутная стрелки часов "
                    "совпадают?",
        "expected": 22,
    },
    {
        "id": "handshake",
        "type": "numeric",
        "question": "В комнате находятся 10 человек. Каждый пожал руку "
                    "каждому ровно один раз. Сколько всего рукопожатий произошло?",
        "expected": 45,
    },
    {
        "id": "concierge",
        "type": "absurd",
        "question": "В доме 12 этажей, на каждом этаже по 18 квартир, в каждой "
                    "квартире не меньше 2 комнат. В каком году умер отец консьержа?",
        "expected": None,
    },
]

# ─── Обертка API ────────────────────────────────────────────────────────────
def ask(messages, model_name, **kwargs):
    if "reasoner" in model_name:
        kwargs.pop("temperature", None)
    try:
        response = client.chat.completions.create(
            model=model_name, messages=messages, **kwargs
        )
        return {
            "content": response.choices[0].message.content,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }
    except Exception as e:
        return {"content": f"ERROR: {e}", "prompt_tokens": 0, "completion_tokens": 0}

# ─── Валидаторы ─────────────────────────────────────────────────────────────

def check_numeric(text, expected):
    """Ищет 'ИТОГ:', берёт оттуда первое число, сравнивает с эталоном."""
    if not text:
        return False, "Empty text"
    match = re.search(r"ИТОГ:\s*(.+)", text, re.IGNORECASE)
    raw_ans = match.group(1) if match else text.strip().split("\n")[-1]
    nums = re.findall(r"[-+]?\d*\.?\d+", raw_ans.replace(",", "."))
    if not nums:
        return False, f"Нет чисел в: {raw_ans[:40]}"
    try:
        parsed = float(nums[0])
    except ValueError:
        return False, f"Не парсится: {nums[0]}"
    is_ok = abs(parsed - float(expected)) < 0.001
    # Красивый вывод: целые числа без ".0"
    display = str(int(parsed)) if parsed == int(parsed) else str(parsed)
    return is_ok, display

def check_absurd(text):
    """Успех = модель отказалась отвечать числом и признала невозможность."""
    if not text:
        return False, "Empty text"
    match = re.search(r"ИТОГ:\s*(.+)", text, re.IGNORECASE)
    raw_ans = match.group(1) if match else text.strip().split("\n")[-1]
    raw_lower = raw_ans.lower()

    # 1. Если модель назвала конкретный год - это галлюцинация
    if re.search(r"\b(19\d{2}|20\d{2})\s*год", raw_lower):
        return False, f"ГАЛЛЮЦИНАЦИЯ (год): {raw_ans[:50]}"

    # 2. Ищем признаки честного отказа
    honest_words = [
        "невозможно", "недостаточно", "нельзя", "нет данн", "неизвестн",
        "не определить", "не указан", "не упоминается", "не содержит",
        "не имеет смысла", "абсурд", "некорректн", "отсутств",
        "не предоставлен", "нет информац", "нет сведен",
    ]
    if any(w in raw_lower for w in honest_words):
        return True, "OK"   # <-- было: f"OK: {raw_ans[:60]}"

    # 3. Если модель просто назвала число (не год) - тоже галлюцинация
    if re.search(r"\d", raw_ans):
        return False, f"ГАЛЛЮЦИНАЦИЯ (число): {raw_ans[:50]}"

    return False, f"Неясный ответ: {raw_ans[:50]}"

def check_answer(task, text):
    if task["type"] == "numeric":
        return check_numeric(text, task["expected"])
    elif task["type"] == "absurd":
        return check_absurd(text)
    return False, "Unknown task type"

# ─── 5 Методов ──────────────────────────────────────────────────────────────

def prompt_direct(q):
    return [{"role": "user",
             "content": q + "\n\nВ конце напиши 'ИТОГ: <ответ>'"}]

def prompt_cot(q):
    return [{"role": "user",
             "content": q + "\n\nРешай пошагово. В конце напиши 'ИТОГ: <ответ>'"}]

def run_meta(q, model_name):
    meta_msgs = [{"role": "user",
                  "content": f"Составь идеальный промпт для решения этой "
                             f"задачи. Не решай её, просто напиши промпт: {q}"}]
    meta_res = ask(meta_msgs, model_name)
    solve_msgs = [{"role": "user",
                   "content": f"{meta_res['content']}\n\nЗадача: {q}\n"
                              f"В конце напиши 'ИТОГ: <ответ>'"}]
    solve_res = ask(solve_msgs, model_name)
    return {
        "content": solve_res["content"],
        "prompt_tokens": meta_res["prompt_tokens"] + solve_res["prompt_tokens"],
        "completion_tokens": meta_res["completion_tokens"] + solve_res["completion_tokens"],
        "intermediate": f"=== ПРОМПТ ОТ МОДЕЛИ ===\n{meta_res['content']}\n\n"
                        f"=== РЕШЕНИЕ ПО НЕМУ ===\n{solve_res['content']}",
    }

def prompt_expert_parallel(q):
    sys_prompt = (
        "Ты — экспертная группа из трёх специалистов: Аналитик, Инженер и Критик.\n"
        "Аналитик разбирает условие и выделяет ключевые данные.\n"
        "Инженер предлагает решение на основе анализа.\n"
        "Критик проверяет решение на наличие логических ошибок.\n"
        "Выслушай всех и вынеси общий финальный вердикт.\n"
        "В конце напиши 'ИТОГ: <ответ>'"
    )
    return [{"role": "system", "content": sys_prompt},
            {"role": "user", "content": q}]

def run_expert_sequential(q, model_name):
    m1 = [{"role": "user",
           "content": f"Ты — Аналитик. Разбери условие задачи, но не решай её: {q}"}]
    a1 = ask(m1, model_name)

    m2 = [{"role": "user",
           "content": f"Ты — Инженер. Аналитик сказал: '{a1['content']}'. "
                      f"Реши задачу на основе этого анализа: {q}. "
                      f"В конце напиши 'ИТОГ: <ответ>'"}]
    a2 = ask(m2, model_name)

    m3 = [{"role": "user",
           "content": f"Ты — Критик. Инженер решил задачу: '{a2['content']}'. "
                      f"Проверь его решение на ошибки. Если всё верно, подтверди. "
                      f"Если ошибка — исправь. В конце напиши 'ИТОГ: <ответ>'"}]
    a3 = ask(m3, model_name)

    return {
        "content": a3["content"],
        "prompt_tokens": a1["prompt_tokens"] + a2["prompt_tokens"] + a3["prompt_tokens"],
        "completion_tokens": (a1["completion_tokens"] + a2["completion_tokens"]
                              + a3["completion_tokens"]),
        "intermediate": f"=== АНАЛИТИК ===\n{a1['content']}\n\n"
                        f"=== ИНЖЕНЕР ===\n{a2['content']}\n\n"
                        f"=== КРИТИК ===\n{a3['content']}",
    }

# ─── Раннер ─────────────────────────────────────────────────────────────────
MODELS = ["deepseek-chat", "deepseek-reasoner"]
METHODS = ["direct", "cot", "meta", "expert_parallel", "expert_sequential"]

stats = defaultdict(lambda: {
    "num_ok": 0, "num_total": 0,
    "abs_ok": 0, "abs_total": 0,
    "time": 0.0, "pt": 0, "ct": 0,
})

print(f"Запуск: {len(TASKS)} задач × {len(MODELS)} модели × {len(METHODS)} методов "
      f"= {len(TASKS) * len(MODELS) * len(METHODS)} прогонов\n")

for model_name in MODELS:
    for method_name in METHODS:
        safe_model = model_name.replace("deepseek-", "")
        detail_file = OUT_DIR / f"{safe_model}_{method_name}.txt"
        print(f"  → {model_name} | {method_name}")

        with open(detail_file, "w", encoding="utf-8") as f:
            f.write(f"ЭКСПЕРИМЕНТ: Модель={model_name}, Метод={method_name}\n")
            f.write("=" * 70 + "\n\n")

            for task in TASKS:
                start_t = time.time()
                intermediate_log = ""

                if method_name == "meta":
                    res = run_meta(task["question"], model_name)
                    intermediate_log = res.get("intermediate", "")
                elif method_name == "expert_sequential":
                    res = run_expert_sequential(task["question"], model_name)
                    intermediate_log = res.get("intermediate", "")
                else:
                    if method_name == "direct":
                        msgs = prompt_direct(task["question"])
                    elif method_name == "cot":
                        msgs = prompt_cot(task["question"])
                    else:  # expert_parallel
                        msgs = prompt_expert_parallel(task["question"])
                    res = ask(msgs, model_name)

                elapsed = time.time() - start_t
                is_correct, verdict = check_answer(task, res["content"])

                print(f"      {task['id']:<10} | "
                      f"{'✓' if is_correct else '✗'} {verdict[:50]}")

                # Детальный лог
                f.write(f"--- ЗАДАЧА: {task['id']} ({task['type']}) ---\n")
                f.write(f"Вопрос: {task['question']}\n")
                f.write(f"Ожидалось: {task['expected']}\n")
                f.write(f"Время: {elapsed:.2f} сек | "
                        f"Prompt: {res['prompt_tokens']} | "
                        f"Completion: {res['completion_tokens']}\n")
                f.write(f"Вердикт: {'ВЕРНО' if is_correct else 'НЕВЕРНО'} "
                        f"({verdict})\n")
                if intermediate_log:
                    f.write(f"\n{intermediate_log}\n")
                f.write(f"\nФИНАЛЬНЫЙ ОТВЕТ:\n{res['content']}\n")
                f.write("-" * 60 + "\n\n")

                # Статистика
                s = stats[f"{model_name} | {method_name}"]
                if task["type"] == "numeric":
                    s["num_total"] += 1
                    if is_correct:
                        s["num_ok"] += 1
                else:
                    s["abs_total"] += 1
                    if is_correct:
                        s["abs_ok"] += 1
                s["time"] += elapsed
                s["pt"] += res["prompt_tokens"]
                s["ct"] += res["completion_tokens"]

# ─── Сводка ─────────────────────────────────────────────────────────────────
summary_path = OUT_DIR / "summary.txt"
with open(summary_path, "w", encoding="utf-8") as f:
    f.write(f"СВОДКА ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
    f.write("=" * 100 + "\n")
    header = (f"{'MODEL':<20} | {'METHOD':<18} | {'NUMERIC':<8} | "
              f"{'ABSURD':<7} | {'TIME (s)':<9} | {'P_TOK':<7} | {'C_TOK':<7}")
    f.write(header + "\n")
    f.write("-" * 100 + "\n")
    for key, s in stats.items():
        f.write(f"{key:<39} | {s['num_ok']}/{s['num_total']:<6} | "
                f"{s['abs_ok']}/{s['abs_total']:<5} | "
                f"{s['time']:<9.2f} | {s['pt']:<7} | {s['ct']:<7}\n")

print(f"\nГотово. Результаты в {OUT_DIR}")