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

MODEL = "deepseek-chat"  # reasoner не принимает temperature
RUNS = 5
TEMPS = [0.0, 0.7, 1.2]

TASKS = [
    {
        "id": "math",
        "type": "deterministic",
        "prompt": "Сколько будет 124 * 45? Напиши ТОЛЬКО итоговое число, без пояснений.",
        "expected": "5580",
    },
    {
        "id": "creative",
        "type": "generative",
        "prompt": "Придумай 3 коротких названия для кофейни, которая специализируется на кофе с собой. Напиши их через запятую.",
        "expected": None,
    },
]

# ─── API ────────────────────────────────────────────────────────────────────
def ask(prompt, temp):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temp,
        )
        return {
            "content": response.choices[0].message.content.strip(),
            "usage": response.usage.completion_tokens,
        }
    except Exception as e:
        return {"content": f"ERROR: {e}", "usage": 0}

# ─── Нормализация для детерминированной задачи ──────────────────────────────
def normalize_math(text):
    # Убираем всё, кроме цифр
    nums = re.findall(r"\d+", text)
    return nums[0] if nums else text

# ─── Раннер ─────────────────────────────────────────────────────────────────
results = defaultdict(list)
stats = defaultdict(lambda: {"correct": 0, "total": 0, "unique": set(), "tokens": 0})

print(f"Запуск: {len(TASKS)} задач × {len(TEMPS)} температур × {RUNS} прогонов "
      f"= {len(TASKS) * len(TEMPS) * RUNS} запросов\n")

for task in TASKS:
    for temp in TEMPS:
        print(f"  → Задача: {task['id']:<12} | temperature = {temp}")
        
        detail_file = OUT_DIR / f"{task['id']}_temp_{temp}.txt"
        with open(detail_file, "w", encoding="utf-8") as f:
            f.write(f"Задача: {task['id']} | Temperature: {temp}\n")
            f.write("=" * 60 + "\n\n")
            
            for run in range(1, RUNS + 1):
                res = ask(task["prompt"], temp)
                content = res["content"]
                
                # Сохраняем в лог
                f.write(f"--- Прогон #{run} ---\n")
                f.write(f"Токены: {res['usage']}\n")
                f.write(f"Ответ:\n{content}\n\n")
                
                # Анализ
                key = f"{task['id']} | temp={temp}"
                results[key].append(content)
                stats[key]["total"] += 1
                stats[key]["tokens"] += res["usage"]
                
                if task["type"] == "deterministic":
                    norm = normalize_math(content)
                    if norm == task["expected"]:
                        stats[key]["correct"] += 1
                    stats[key]["unique"].add(norm)
                    status = "✓" if norm == task["expected"] else "✗"
                    print(f"      Прогон {run}: {status} {norm}")
                else:
                    # Для творческой - просто добавляем в уникальные
                    stats[key]["unique"].add(content)
                    print(f"      Прогон {run}: {content[:60]}...")

# ─── Сводка ─────────────────────────────────────────────────────────────────
summary_path = OUT_DIR / "summary.txt"
with open(summary_path, "w", encoding="utf-8") as f:
    f.write(f"СВОДКА ПО ТЕМПЕРАТУРЕ ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
    f.write("=" * 90 + "\n")
    f.write(f"{'TASK':<15} | {'TEMP':<5} | {'CORRECT':<9} | {'UNIQUE':<8} | {'TOKENS':<8}\n")
    f.write("-" * 90 + "\n")
    
    for key, s in stats.items():
        task_name, temp_str = key.split(" | ")
        temp_val = temp_str.replace("temp=", "")
        unique_count = len(s["unique"])
        correct_str = f"{s['correct']}/{s['total']}" if "math" in task_name else "—"
        
        f.write(f"{task_name:<15} | {temp_val:<5} | {correct_str:<9} | "
                f"{unique_count}/{s['total']:<6} | {s['tokens']:<8}\n")

print(f"\nГотово. Результаты в {OUT_DIR}")