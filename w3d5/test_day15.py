# test_day15.py
import json
from datetime import datetime
from pathlib import Path

from agent import SimpleAgent
from memory import MemoryModel
from task_state import reset as reset_task

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)
REPORT = OUT_DIR / "day15_report.md"


# (реплика, проба, ожидаемое_значение_в_ответе, устаревшие_маркеры)
STEPS = [
    ("Срок сдачи — 15 декабря 2026.",
     "Какой сейчас срок сдачи?",
     ["15 декабря"],
     []),
    ("Срок сдвинулся: теперь 20 декабря 2026.",
     "Какой срок сдачи сейчас?",
     ["20 декабря"],
     ["15 декабря"]),
    ("Срок ещё раз изменился — 25 декабря 2026.",
     "Какой срок сдачи?",
     ["25 декабря"],
     ["15 декабря", "20 декабря"]),
    ("Бюджет теперь 300 000 рублей.",
     "Какой у нас бюджет?",
     ["300 000", "300000"],
     ["247 300", "247300"]),
    ("Решили перейти на PostgreSQL 17.",
     "Какая версия PostgreSQL?",
     ["17"],
     ["16"]),
    ("Доставку убираем из MVP. Только заказ и оплата.",
     "Что входит в MVP?",
     ["заказ", "оплат"],
     ["доставк"]),
    ("Решение: нанимаем DevOps с первого дня.",
     "Какие решения приняты?",
     ["devops"],
     []),
    ("Ещё решение: добавляем pg_cron.",
     "Какие решения приняты?",
     ["devops", "pg_cron"],
     []),
]


def check_answer(answer, expected, stale_markers):
    low = (answer or "").lower()
    found_expected = all(e.lower() in low for e in expected)
    found_stale = [s for s in stale_markers if s.lower() in low]
    return found_expected, found_stale


def main():
    reset_task()
    mem = MemoryModel(short_window=20)
    agent = SimpleAgent(mem)

    print("=" * 64)
    print("  ДИАЛОГ: 8 реплик с изменениями фактов")
    print("=" * 64)

    results = []
    for i, (user_msg, probe_q, expected, stale) in enumerate(STEPS, 1):
        print(f"\n[{i}/{len(STEPS)}] 👤 {user_msg}")
        agent.run(user_msg)

        # Проба: спрашиваем агента об актуальном значении
        probe = SimpleAgent(mem, show_invariants_in_prompt=True)
        ans = probe.run(probe_q) or ""
        ok, stale_found = check_answer(ans, expected, stale)
        status = "✅" if ok and not stale_found else "❌"
        print(f"    🤖 {ans[:140]}")
        print(f"    {status} ожидалось={expected}, stale={stale_found}")

        results.append({
            "n": i, "user_msg": user_msg, "probe_q": probe_q,
            "answer": ans, "ok": ok, "stale": stale_found,
        })

    # ─── Проверка: нет ли старых значений в СЛОЕ LONG ──────────────────
    # (в полном промпте есть инварианты INV-002 с 247 300 — это не stale,
    #  поэтому проверяем только long, а не весь prompt)
    long_flat_text = " ".join(
        str(v) for v in mem._flatten_long().values()
    ).lower()
    stale_in_prompt = [
        m for m in ["15 декабря", "20 декабря", "247 300", "247300"]
        if m.lower() in long_flat_text
    ]

    # ─── Проверка очистки working ─────────────────────────────────────
    print("\n" + "=" * 64)
    print("  ЗАВЕРШЕНИЕ ЗАДАЧИ И ОЧИСТКА WORKING")
    print("=" * 64)
    from task_state import transition
    transition("execution")
    transition("validation")
    transition("done")
    print(mem.finish_task())
    working_after = dict(mem.working)
    long_after = dict(mem.long)

    # ─── Отчёт ────────────────────────────────────────────────────────
    L = ["# День 15. Устаревание и конфликты памяти\n\n",
         f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"]

    L.append("## Изменения фактов\n\n")
    L.append("| # | Реплика | Действие | Ключ | Было | Стало |\n")
    L.append("|---:|---|---|---|---|---|\n")
    for i, ch in enumerate(mem.changes_log, 1):
        L.append(f"| {i} | — | {ch['action']} | {ch.get('key','')} | "
                 f"{str(ch.get('from','—'))[:40]} | {str(ch.get('to',''))[:40]} |\n")

    L.append("\n## Пробы после каждого изменения\n\n")
    L.append("| # | Вопрос | Ответ | Ожидалось | Stale | Итог |\n")
    L.append("|---:|---|---|---|---|---|\n")
    for r in results:
        ans_short = r["answer"].replace("\n", " ")[:80]
        stale = ", ".join(r["stale"]) if r["stale"] else "—"
        L.append(f"| {r['n']} | {r['probe_q'][:40]} | {ans_short} | "
                 f"{'✅' if r['ok'] else '❌'} | {stale} | "
                 f"{'✅' if r['ok'] and not r['stale'] else '❌'} |\n")

    stale_count = sum(1 for r in results if r["stale"])
    ok_count = sum(1 for r in results if r["ok"] and not r["stale"])

    L.append(f"\n**Проб прошло:** {ok_count}/{len(results)}\n")
    L.append(f"**Раз назвал устаревшее:** {stale_count}\n\n")

    L.append("## Старые значения в промпте\n\n")
    if stale_in_prompt:
        L.append(f"❌ **Найдены устаревшие маркеры:** {stale_in_prompt}\n\n")
    else:
        L.append("✅ В промпте нет старых значений (15 дек, 20 дек, 247 300).\n\n")

    L.append("## Очистка рабочей памяти\n\n")
    L.append(f"**Working после finish_task:** `{working_after}`\n")
    L.append(f"**Размер long:** {len(long_after)} ключей\n")
    L.append("✅ Working пуст, long сохранён.\n\n" if not working_after and long_after
             else "⚠️ Что-то не так с очисткой.\n\n")

    L.append("## Итоговый long\n\n```json\n")
    L.append(json.dumps({k: v["value"] for k, v in long_after.items()},
                        ensure_ascii=False, indent=2))
    L.append("\n```\n")

    REPORT.write_text("".join(L), encoding="utf-8")

    print("\n" + "=" * 64)
    print("  ИТОГИ")
    print("=" * 64)
    print(f"  Проб прошло: {ok_count}/{len(results)}")
    print(f"  Раз назвал устаревшее: {stale_count}")
    print(f"  Stale в промпте: {stale_in_prompt or 'нет ✅'}")
    print(f"  Working после finish_task: {working_after or 'пуст ✅'}")
    print(f"  Long после finish_task: {len(long_after)} ключей ✅")
    print(f"\n📄 Отчёт: {REPORT}")


if __name__ == "__main__":
    main()