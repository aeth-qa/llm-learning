import time
import re
from datetime import datetime
from openai import OpenAI
from pathlib import Path
from collections import defaultdict

# ─── Конфиг ─────────────────────────────────────────────────────────────────
# Читаем ключ OpenRouter (лежит рядом с key.deepseek)
key_file = Path(__file__).parent.parent / "key.openapi"
API_KEY = key_file.read_text(encoding="utf-8").strip()

client = OpenAI(
    api_key=API_KEY,
    base_url="https://openrouter.ai/api/v1",
    timeout=60.0,
    default_headers={
        "HTTP-Referer": "http://localhost",
        "X-Title": "LLM Learning Day 5",
    }
)

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)

RUNS = 3

# ─── Конфигурация моделей ───────────────────────────────────────────────────
# Цены указаны в долларах за 1 МИЛЛИОН токенов (вход / выход).
# Если модель вернет 404, обновите ID на актуальный в кабинете OpenRouter.
MODELS = [
    {
        "label": "Small (Qwen3.5-9B)",
        "id": "qwen/qwen3.5-9b",
        "price_in": 0.05,
        "price_out": 0.05,  # Уточните точную цену выхода на странице модели
        "supports_temperature": True,
    },
    {
        "label": "Medium (Claude Haiku)",
        "id": "anthropic/claude-haiku-5.5",
        "price_in": 0.10,
        "price_out": 0.50,
        "supports_temperature": True,
    },
    {
        "label": "Flagship (Claude Sonnet)",
        "id": "anthropic/claude-sonnet-5",
        "price_in": 2.00,
        "price_out": 10.00,
        "supports_temperature": True,
    },
]

# ─── Задачи (те же, что в Дне 3) ────────────────────────────────────────────
TASKS = [
    {"id": "sheep", "type": "numeric", "expected": 9, 
     "question": "У фермера было 17 овец. Все, кроме 9, убежали. Сколько овец осталось у фермера?"},
    {"id": "snail", "type": "numeric", "expected": 8, 
     "question": "Улитка ползет по столбу высотой 10 метров. За день она поднимается на 3 метра, а за ночь сползает на 2 метра. За сколько дней улитка доберется до вершины?"},
    {"id": "lily", "type": "numeric", "expected": 47, 
     "question": "Кувшинки в пруду удваивают свою площадь каждый день. Если они полностью покрывают пруд за 48 дней, за сколько дней они покроют ровно половину пруда?"},
    {"id": "clock", "type": "numeric", "expected": 22, 
     "question": "Сколько раз в сутки часовая и минутная стрелки часов совпадают?"},
    {"id": "handshake", "type": "numeric", "expected": 45, 
     "question": "В комнате находятся 10 человек. Каждый пожал руку каждому ровно один раз. Сколько всего рукопожатий произошло?"},
    {"id": "concierge", "type": "absurd", "expected": None, 
     "question": "В доме 12 этажей, на каждом этаже по 18 квартир, в каждой квартире не меньше 2 комнат. В каком году умер отец консьержа?"},
]

# ─── Валидаторы (с косметическими правками из Дня 3) ────────────────────────
def check_numeric(text, expected):
    if not text: return False, "Empty text"
    match = re.search(r"ИТОГ:\s*(.+)", text, re.IGNORECASE)
    raw_ans = match.group(1) if match else text.strip().split("\n")[-1]
    nums = re.findall(r"[-+]?\d*\.?\d+", raw_ans.replace(",", "."))
    if not nums: return False, f"Нет чисел в: {raw_ans[:40]}"
    try: parsed = float(nums[0])
    except ValueError: return False, f"Не парсится: {nums[0]}"
    is_ok = abs(parsed - float(expected)) < 0.001
    display = str(int(parsed)) if parsed == int(parsed) else str(parsed)
    return is_ok, display

def check_absurd(text):
    if not text: return False, "Empty text"
    match = re.search(r"ИТОГ:\s*(.+)", text, re.IGNORECASE)
    raw_ans = match.group(1) if match else text.strip().split("\n")[-1]
    raw_lower = raw_ans.lower()
    if re.search(r"\b(19\d{2}|20\d{2})\s*год", raw_lower):
        return False, f"ГАЛЛЮЦИНАЦИЯ (год): {raw_ans[:50]}"
    honest_words = [
        "невозможно", "недостаточно", "нельзя", "нет данн", "неизвестн",
        "не определить", "не указан", "не упоминается", "не содержит",
        "не имеет смысла", "абсурд", "некорректн", "отсутств",
        "не предоставлен", "нет информац", "нет сведен",
        "не имеет решения", "нет ответа", "ответа нет", "не хватает информации", 
        "не хватает данных"
    ]
    if any(w in raw_lower for w in honest_words): return True, "OK"
    if re.search(r"\d", raw_ans): return False, f"ГАЛЛЮЦИНАЦИЯ (число): {raw_ans[:50]}"
    return False, f"Неясный ответ: {raw_ans[:50]}"

def check_answer(task, text):
    if task["type"] == "numeric": return check_numeric(text, task["expected"])
    return check_absurd(text)

# ─── Обертка API ────────────────────────────────────────────────────────────
def ask(prompt, model_cfg, max_retries=3):
    kwargs = {"temperature": 0.0} if model_cfg["supports_temperature"] else {}
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_cfg["id"],
                messages=[{"role": "user", "content": prompt + "\n\nВ конце напиши 'ИТОГ: <ответ>'"}],
                max_tokens=1024,
                **kwargs
            )
            return {
                "content": response.choices[0].message.content,
                "pt": response.usage.prompt_tokens,
                "ct": response.usage.completion_tokens,
            }
        except Exception as e:
            if attempt == max_retries - 1:
                return {"content": f"ERROR after {max_retries} attempts: {e}", "pt": 0, "ct": 0}
            
            wait_time = 2 * (attempt + 1)
            print(f"      ⚠️ Ошибка (попытка {attempt+1}/{max_retries}), жду {wait_time}с: {str(e)[:60]}")
            time.sleep(wait_time)

# ─── Раннер ─────────────────────────────────────────────────────────────────
stats = defaultdict(lambda: {
    "correct": 0, "total": 0, "time": 0.0, 
    "pt": 0, "ct": 0, "cost": 0.0
})

print(f"Запуск: {len(TASKS)} задач × {len(MODELS)} модели × {RUNS} прогонов\n")

for m_cfg in MODELS:
    label = m_cfg["label"]
    safe_label = label.split(" ")[0] # "Small", "Medium", "Flagship"
    detail_file = OUT_DIR / f"{safe_label}.txt"
    
    print(f"  → {label} ({m_cfg['id']})")
    
    with open(detail_file, "w", encoding="utf-8") as f:
        f.write(f"МОДЕЛЬ: {label} | ID: {m_cfg['id']}\n")
        f.write(f"Цены (вход/выход на 1M): ${m_cfg['price_in']} / ${m_cfg['price_out']}\n")
        f.write("=" * 70 + "\n\n")
        
        for task in TASKS:
            for run in range(1, RUNS + 1):
                start_t = time.time()
                res = ask(task["question"], m_cfg)
                elapsed = time.time() - start_t
                
                is_ok, verdict = check_answer(task, res["content"])
                
                # Считаем стоимость для конкретного запроса
                cost = (res["pt"] / 1_000_000 * m_cfg["price_in"]) + \
                       (res["ct"] / 1_000_000 * m_cfg["price_out"])
                
                # Запись в детальный лог
                f.write(f"--- {task['id']} | Прогон #{run} ---\n")
                f.write(f"Время: {elapsed:.2f} сек | Токены: {res['pt']} / {res['ct']} | Стоимость: ${cost:.6f}\n")
                f.write(f"Вердикт: {'ВЕРНО' if is_ok else 'НЕВЕРНО'} ({verdict})\n")
                f.write(f"Ответ:\n{res['content']}\n\n")
                
                # Накапливаем статистику по модели
                s = stats[label]
                s["total"] += 1
                if is_ok: s["correct"] += 1
                s["time"] += elapsed
                s["pt"] += res["pt"]
                s["ct"] += res["ct"]
                s["cost"] += cost
                
                # Прогресс в консоль
                status = "✓" if is_ok else "✗"
                print(f"      {task['id']:<10} #{run} | {status} {verdict[:30]:<30} | {elapsed:.1f}с")
                
                # Небольшая пауза, чтобы не злить rate-limit OpenRouter
                time.sleep(1) 

# ─── Сводка ─────────────────────────────────────────────────────────────────
summary_path = OUT_DIR / "summary.txt"
with open(summary_path, "w", encoding="utf-8") as f:
    f.write(f"СВОДКА ПО МОДЕЛЯМ ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
    f.write("=" * 105 + "\n")
    header = (f"{'MODEL':<15} | {'CORRECT':<7} | {'TIME(s)':<8} | "
              f"{'TOTAL_TOK':<9} | {'COST($)':<10} | {'AVG_TIME':<8} | {'AVG_COST':<9}")
    f.write(header + "\n")
    f.write("-" * 105 + "\n")
    
    for label, s in stats.items():
        avg_time = s["time"] / s["total"]
        avg_cost = s["cost"] / s["total"]
        total_tok = s["pt"] + s["ct"]
        
        f.write(f"{label:<15} | {s['correct']}/{s['total']:<5} | "
                f"{s['time']:<8.1f} | {total_tok:<9} | "
                f"${s['cost']:<9.5f} | {avg_time:<8.2f} | ${avg_cost:<8.6f}\n")

    f.write("\n\n=== Сравнение с Small (Qwen) ===\n")
    small_cost = stats["Small (Qwen3.5-9B)"]["cost"]
    small_correct = stats["Small (Qwen3.5-9B)"]["correct"]
    
    for label, s in stats.items():
        if "Small" in label: continue
        cost_ratio = s["cost"] / small_cost if small_cost > 0 else 0
        diff_correct = s["correct"] - small_correct
        f.write(f"{label}:\n")
        f.write(f"  Дороже в {cost_ratio:.1f} раз\n")
        f.write(f"  Дополнительно решено задач: {diff_correct}\n")

print(f"\nГотово. Результаты в {OUT_DIR}")