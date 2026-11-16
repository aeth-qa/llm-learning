# test_day9.py
from datetime import datetime
from agent import SimpleAgent
from storage import OUT_DIR, reset_all
from token_counter import estimate_cost

REPORT_FILE = OUT_DIR / "day9_report.md"

# ─── Диалог: 15 реплик = 30 сообщений, 7 деталей вплетены в первые 7 ────────
DIALOGUE = [
    "Привет, меня зовут Игорь. Будем работать над проектом.",
    "Проект называется «Кофе-тайм» — это приложение для заказа кофе.",
    "Бюджет — 250 000 рублей. Это финальная сумма, больше не будет.",
    "Срок жёсткий: сдать нужно до 15 декабря 2026.",
    "База данных — PostgreSQL. MongoDB не подходит, нужны транзакции.",
    "Бренд-цвет — тёмно-зелёный, hex #2E8B57. Логотип будет на нём.",
    "Команда в Москве, работаем по МСК (UTC+3).",
    "Какие риски ты видишь у такого проекта?",
    "А что по архитектуре посоветуешь?",
    "Как лучше тестировать?",
    "Что думаешь о сроках — реально уложиться?",
    "Ещё вопрос: как монетизировать будем?",
    "Какие метрики отслеживать?",
    "Спасибо за советы. Что-нибудь упустили?",
    "Ок, двигаемся дальше.",
]

DETAILS = [
    {"name": "Имя", "probe": "Как меня зовут?",
     "expect": ["игор"]},
    {"name": "Проект", "probe": "Как называется проект?",
     "expect": ["кофе-тайм", "кофе тайм", "кофе-тайм"]},
    {"name": "Бюджет", "probe": "Какой у нас бюджет?",
     "expect": ["250 000", "250000", "250 тыс", "250k", "250.000"]},
    {"name": "Срок", "probe": "Какой срок сдачи?",
     "expect": ["15 декабря", "15.12", "декабря 2026", "15.12.2026"]},
    {"name": "База", "probe": "Какую базу данных выбрали?",
     "expect": ["postgresql", "postgres", "постгрес"]},
    {"name": "Цвет", "probe": "Какой цвет бренда?",
     "expect": ["2e8b57", "тёмно-зелёный", "темно-зеленый", "тёмно зеленый", "темно зеленый"]},
    {"name": "Пояс", "probe": "Какой часовой пояс у команды?",
     "expect": ["мск", "utc+3", "московск", "msk"]},
]


def _check(answer, expect):
    if not answer:
        return False
    low = answer.lower()
    return any(e.lower() in low for e in expect)


def run_mode(mode_name, use_compression):
    print(f"\n{'=' * 62}")
    print(f"  РЕЖИМ: {mode_name}")
    print(f"{'=' * 62}\n")

    reset_all()
    agent = SimpleAgent(use_compression=use_compression, persist=True)

    for i, msg in enumerate(DIALOGUE, 1):
        print(f"\n  [Диалог {i}/{len(DIALOGUE)}]")
        agent.run(msg)

    print(f"\n  ─── После {len(DIALOGUE)} реплик ───")
    print(f"  Hot-история: {len(agent.history)} сообщений")
    print(f"  Summary: {agent.summary[:120]}..." if agent.summary else "  Summary: (пусто)")
    print(f"  Prompt (диалог): {agent.session_stats['prompt_tokens']}")
    print(f"  Prompt (сжатие): {agent.compression_stats['prompt_tokens']}")

    state = {"history": list(agent.history), "summary": agent.summary}

    print(f"\n  ─── Проверка {len(DETAILS)} деталей ───")
    details_check = {}
    for d in DETAILS:
        probe = SimpleAgent(
            use_compression=False,
            initial_state=state,
            persist=False,   # не пишем на диск, не портим основное состояние
        )
        answer = probe.run(d["probe"])
        found = _check(answer, d["expect"])
        details_check[d["name"]] = found
        mark = "✅" if found else "❌"
        print(f"  [{d['name']:<8}] {mark}  {(answer or '')[:70]}")

    return {
        "mode": mode_name,
        "request_prompt_tokens": agent.session_stats["prompt_tokens"],
        "request_completion_tokens": agent.session_stats["completion_tokens"],
        "compression_prompt_tokens": agent.compression_stats["prompt_tokens"],
        "compression_completion_tokens": agent.compression_stats["completion_tokens"],
        "total_prompt_tokens": agent.session_stats["prompt_tokens"] + agent.compression_stats["prompt_tokens"],
        "total_completion_tokens": agent.session_stats["completion_tokens"] + agent.compression_stats["completion_tokens"],
        "details_found": sum(details_check.values()),
        "details_check": details_check,
        "final_summary": agent.summary,
        "final_history_size": len(agent.history),
    }


def generate_report(results):
    lines = []
    lines.append("# День 9. Управление контекстом: сжатие истории\n\n")
    lines.append(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    lines.append(f"Диалог: {len(DIALOGUE)} реплик ({len(DIALOGUE) * 2} сообщений)\n")
    lines.append(f"KEEP_RECENT = 10, COMPRESS_STEP = 10\n\n")

    lines.append("## Сводная таблица\n\n")
    lines.append("| Режим | Prompt (диалог) | Prompt (сжатие) | Всего prompt | "
                 "Completion | Стоимость | Деталей |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for r in results:
        cost = estimate_cost(r["total_prompt_tokens"], r["total_completion_tokens"])
        lines.append(
            f"| {r['mode']} | {r['request_prompt_tokens']} | "
            f"{r['compression_prompt_tokens']} | {r['total_prompt_tokens']} | "
            f"{r['total_completion_tokens']} | ${cost:.4f} | "
            f"{r['details_found']}/{len(DETAILS)} |\n"
        )

    lines.append("\n## Детали по каждому факту\n\n")
    lines.append("| Деталь | Без сжатия | Со сжатием |\n")
    lines.append("|---|---|---|\n")
    for d in DETAILS:
        row = []
        for r in results:
            row.append("✅" if r["details_check"][d["name"]] else "❌")
        lines.append(f"| {d['name']} | {row[0]} | {row[1]} |\n")

    lines.append("\n## Итоговое summary (режим «Со сжатием»)\n\n")
    for r in results:
        if "сжатием" in r["mode"] and "Без" not in r["mode"]:
            lines.append("```\n" + (r["final_summary"] or "(пусто)") + "\n```\n")

    REPORT_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"\n📄 Отчёт сохранён: {REPORT_FILE}")


if __name__ == "__main__":
    results = []
    results.append(run_mode("Без сжатия", use_compression=False))
    results.append(run_mode("Со сжатием", use_compression=True))

    generate_report(results)

    print("\n" + "=" * 62)
    print("  ИТОГИ")
    print("=" * 62)
    for r in results:
        print(f"  {r['mode']:<14} | Деталей {r['details_found']}/{len(DETAILS)} | "
              f"Prompt всего {r['total_prompt_tokens']} | "
              f"Сжатие {r['compression_prompt_tokens']} | "
              f"Hot-история {r['final_history_size']}")

    print("\n💡 Для чистого старта main.py после теста выполните:")
    print("   py -c \"from storage import reset_all; reset_all()\"")