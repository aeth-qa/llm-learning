# test_day12.py
import re
from datetime import datetime
from pathlib import Path

from agent import SimpleAgent
from memory import MemoryModel


OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)
REPORT = OUT_DIR / "day12_report.md"


# ─── Профили с противоположными предпочтениями ──────────────────────────────
PROFILES = {
    "A (кратко, формально, без кода)": {
        "стиль": "кратко, 1–2 предложения",
        "формат": "без кода, без markdown",
        "тон": "формально, на «Вы»",
        "ограничения": ["без эмодзи", "без примеров кода"],
    },
    "B (подробно, неформально, с кодом)": {
        "стиль": "подробно, с примерами",
        "формат": "с блоками кода",
        "тон": "неформально, на «ты», дружелюбно",
        "ограничения": [],
    },
    "C (сбалансированно, дружелюбно)": {
        "стиль": "средней длины, по делу",
        "формат": "можно списки",
        "тон": "дружелюбно, но без панибратства",
        "ограничения": ["без длинных эссе"],
    },
}

QUESTION = "Как в Python проверить, есть ли ключ в словаре?"

# ─── Эвристики проверки предпочтений ────────────────────────────────────────
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")

def word_count(text):
    return len(text.split())

def is_brief(text):
    return word_count(text) < 80

def is_verbose(text):
    return word_count(text) > 150
    
def is_balanced(text):
    """Сбалансированный ответ — не слишком краткий, не эссе."""
    return 60 <= word_count(text) <= 200

def has_code(text):
    return "```" in text

def no_code(text):
    return "```" not in text

def is_formal(text):
    low = text.lower()
    if EMOJI_RE.search(text): return False
    if re.search(r"\b(привет|дружище|слышь|братан|брат)\b", low): return False
    if "!" in text: return False
    return True

def is_informal(text):
    low = text.lower()
    if EMOJI_RE.search(text): return True
    if re.search(r"\b(привет|дружище|слышь|братан|брат)\b", low): return True
    if "!" in text: return True
    return False


# ─── Часть 1: три профиля на одном вопросе ──────────────────────────────────
def run_three_profiles():
    print("=" * 64)
    print("  ЧАСТЬ 1: три профиля на одном вопросе")
    print("=" * 64)

    results = {}
    for name, profile in PROFILES.items():
        print(f"\n  → {name}")
        mem = MemoryModel(short_window=10)
        mem.replace_layers({}, {}, profile)
        agent = SimpleAgent(mem)
        answer = agent.run(QUESTION, extract=False) or ""
        print(f"    {answer[:160]}")

        checks = {}
        if "кратко" in profile["стиль"]:
            checks["кратко (<80 слов)"] = is_brief(answer)
        if "подробно" in profile["стиль"]:
            checks["подробно (>200 слов)"] = is_verbose(answer)
        if "с кодом" in profile["формат"]:
            checks["с кодом"] = has_code(answer)
        if "без кода" in profile["формат"]:
            checks["без кода"] = no_code(answer)
        if "формально" in profile["тон"]:
            checks["формально"] = is_formal(answer)
        if "неформально" in profile["тон"]:
            checks["неформально"] = is_informal(answer)
        if "средней длины" in profile["стиль"]:
            checks["средней длины (60–200 слов)"] = is_balanced(answer)

        results[name] = {
            "answer": answer,
            "words": word_count(answer),
            "checks": checks,
            "passed": sum(checks.values()),
            "total": len(checks),
        }
    return results


# ─── Часть 2: 10 вопросов в одном профиле (устойчивость) ────────────────────
STABILITY_QUESTIONS = [
    "Что такое список в Python?",
    "Как создать функцию?",
    "Что такое модуль?",
    "Как обработать исключение?",
    "Что такое генератор?",
    "Как работает срез списка?",
    "Что такое декоратор?",
    "Как склеить две строки?",
    # 9–10: стресс-вопросы, где краткость противоречит содержанию
    "Опиши, как работает сборщик мусора (GC) в CPython. [СТРЕСС]",
    "В чём разница между asyncio, threading и multiprocessing? [СТРЕСС]",
]

def run_stability():
    print("\n" + "=" * 64)
    print("  ЧАСТЬ 2: устойчивость профиля A на 10 вопросах")
    print("=" * 64)

    mem = MemoryModel(short_window=10)
    mem.replace_layers({}, {}, PROFILES["A (кратко, формально, без кода)"])
    agent = SimpleAgent(mem)

    rows = []
    for i, q in enumerate(STABILITY_QUESTIONS, 1):
        answer = agent.run(q) or ""
        wc = word_count(answer)
        ok = is_brief(answer) and no_code(answer) and is_formal(answer)
        rows.append({
            "n": i, "q": q, "words": wc, "ok": ok,
            "stress": "[СТРЕСС]" in q,
            "answer": answer[:100],
        })
        tag = "🔥" if "[СТРЕСС]" in q else "  "
        mark = "✅" if ok else "❌"
        print(f"  [{i:>2}/10] {tag}{mark} слов={wc:>3}  {q[:45]}")

    return rows


# ─── Отчёт ──────────────────────────────────────────────────────────────────
def generate_report(profiles_result, stability_rows):
    L = ["# День 12. Персонализация ассистента\n\n",
         f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n",
         f"Вопрос для всех профилей: _{QUESTION}_\n\n"]

    # ─── Часть 1: таблица ──────────────────────────────────────────────
    L.append("## Часть 1: три профиля на одном вопросе\n\n")
    L.append("| Профиль | Слов | Пройдено проверок | Что проверяли |\n")
    L.append("|---|---:|---:|---|\n")
    for name, r in profiles_result.items():
        passed = ", ".join(f"{k}: {'✅' if v else '❌'}" for k, v in r["checks"].items())
        L.append(f"| {name} | {r['words']} | {r['passed']}/{r['total']} | {passed} |\n")

    # ─── Часть 1: полные ответы ────────────────────────────────────────
    L.append("\n### Полные ответы\n\n")
    for name, r in profiles_result.items():
        L.append(f"**{name}** (слов: {r['words']}):\n\n")
        L.append("```\n" + r["answer"].strip() + "\n```\n\n")

    # ─── Часть 2: устойчивость (вне цикла!) ────────────────────────────
    L.append("## Часть 2: устойчивость профиля A на 10 вопросах\n\n")
    L.append("| № | Тип | Вопрос | Слов | Соблюдено |\n")
    L.append("|---:|---|---|---:|:---:|\n")
    for r in stability_rows:
        typ = "🔥 стресс" if r.get("stress") else "обычный"
        q_short = r["q"].replace(" [СТРЕСС]", "")[:60]
        L.append(f"| {r['n']} | {typ} | {q_short} | {r['words']} | "
                 f"{'✅' if r['ok'] else '❌'} |\n")

    simple = [r for r in stability_rows if not r.get("stress")]
    stress = [r for r in stability_rows if r.get("stress")]

    first_simple = next((r["n"] for r in simple if not r["ok"]), None)
    first_stress = next((r["n"] for r in stress if not r["ok"]), None)

    L.append(f"\n**Первая проблема на обычных вопросах:** "
             + (f"№{first_simple}" if first_simple else "не наступила") + "\n")
    L.append(f"**Первая проблема на стресс-вопросах:** "
             + (f"№{first_stress}" if first_stress else "не наступила") + "\n")

    REPORT.write_text("".join(L), encoding="utf-8")
    print(f"\n📄 Отчёт: {REPORT}")


if __name__ == "__main__":
    profiles_result = run_three_profiles()
    stability_rows = run_stability()
    generate_report(profiles_result, stability_rows)

    print("\n" + "=" * 64)
    print("  ИТОГИ")
    print("=" * 64)
    for name, r in profiles_result.items():
        print(f"  {name:<34} | слов {r['words']:>3} | "
              f"проверок {r['passed']}/{r['total']}")
    first_break = next((r["n"] for r in stability_rows if not r["ok"]), None)
    print(f"\n  Устойчивость: первый сбой "
          + (f"на вопросе {first_break}" if first_break else "не наступил"))