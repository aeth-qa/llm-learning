# test_day10.py
import inspect
from datetime import datetime
from pathlib import Path

from agent import SimpleAgent
from strategies import (
    SlidingWindowStrategy, StickyFactsStrategy, SummaryStrategy,
)
from token_counter import estimate_cost


OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)
REPORT_FILE = OUT_DIR / "day10_report.md"

# Тот же диалог и те же детали, что в Дне 9
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
    {"name": "Имя",    "probe": "Как меня зовут?",                 "expect": ["игор"]},
    {"name": "Проект", "probe": "Как называется проект?",          "expect": ["кофе-тайм", "кофе тайм"]},
    {"name": "Бюджет", "probe": "Какой у нас бюджет?",             "expect": ["250 000", "250000", "250 тыс"]},
    {"name": "Срок",   "probe": "Какой срок сдачи?",               "expect": ["15 декабря", "15.12", "декабря 2026"]},
    {"name": "База",   "probe": "Какую базу данных выбрали?",      "expect": ["postgresql", "postgres"]},
    {"name": "Цвет",   "probe": "Какой цвет бренда?",              "expect": ["2e8b57", "тёмно-зелёный", "темно-зеленый"]},
    {"name": "Пояс",   "probe": "Какой часовой пояс у команды?",   "expect": ["мск", "utc+3", "московск"]},
]


def count_loc(cls):
    try:
        src = inspect.getsource(cls)
    except OSError:
        return 0
    return len([l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")])


def check_answer(answer, expect):
    if not answer:
        return False
    low = answer.lower()
    return any(e.lower() in low for e in expect)


def run_strategy(strategy_factory, name):
    print(f"\n{'=' * 64}\n  СТРАТЕГИЯ: {name}\n{'=' * 64}")

    agent = SimpleAgent(strategy_factory())
    for i, msg in enumerate(DIALOGUE, 1):
        print(f"  [{i:2d}/{len(DIALOGUE)}] {msg[:55]}")
        agent.run(msg)

    cp = OUT_DIR / f"checkpoint_{name.replace(' ', '_').lower()}.json"
    agent.save_checkpoint(cp)

    print(f"\n  ─── Пробы ───")
    details_check = {}
    for d in DETAILS:
        probe = SimpleAgent(strategy_factory())
        probe.load_checkpoint(cp)
        answer = probe.run(d["probe"]) or ""
        found = check_answer(answer, d["expect"])
        details_check[d["name"]] = found
        print(f"    [{d['name']:<8}] {'✅' if found else '❌'}  {answer[:60]}")

    return {
        "name": name,
        "details_found": sum(details_check.values()),
        "details_total": len(DETAILS),
        "details_check": details_check,
        "dialog_prompt": agent.session_stats["dialog_prompt_tokens"],
        "dialog_completion": agent.session_stats["dialog_completion_tokens"],
        "dialog_calls": agent.session_stats["dialog_calls"],
        "mgmt_calls": agent.strategy.stats["management_calls"],
        "mgmt_prompt": agent.strategy.stats["management_prompt_tokens"],
        "mgmt_completion": agent.strategy.stats["management_completion_tokens"],
        "loc": count_loc(type(agent.strategy)),
    }


def generate_report(results):
    lines = ["# День 10. Сравнение стратегий управления контекстом\n\n"]
    lines.append(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    lines.append(f"Диалог: {len(DIALOGUE)} реплик, {len(DETAILS)} деталей. "
                 f"Все стратегии с keep_recent=10.\n\n")
    lines.append("## Сводная таблица\n\n")
    lines.append("| Стратегия | Деталей | Prompt (диалог) | Prompt (управление) | "
                 "Всего prompt | Completion | Стоимость | Управляющих вызовов | Строк кода |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results:
        tp = r["dialog_prompt"] + r["mgmt_prompt"]
        tc = r["dialog_completion"] + r["mgmt_completion"]
        cost = estimate_cost(tp, tc)
        lines.append(f"| {r['name']} | {r['details_found']}/{r['details_total']} | "
                     f"{r['dialog_prompt']} | {r['mgmt_prompt']} | "
                     f"{tp} | {tc} | ${cost:.4f} | {r['mgmt_calls']} | {r['loc']} |\n")

    lines.append("\n## Детали по каждому факту\n\n")
    lines.append("| Деталь | " + " | ".join(r["name"] for r in results) + " |\n")
    lines.append("|---|" + "---|" * len(results) + "\n")
    for d in DETAILS:
        row = ["✅" if r["details_check"][d["name"]] else "❌" for r in results]
        lines.append(f"| {d['name']} | " + " | ".join(row) + " |\n")

    REPORT_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"\n📄 Отчёт: {REPORT_FILE}")


if __name__ == "__main__":
    results = [
        run_strategy(lambda: SlidingWindowStrategy(keep_recent=10), "Sliding Window"),
        run_strategy(lambda: StickyFactsStrategy(keep_recent=10), "Sticky Facts"),
        run_strategy(lambda: SummaryStrategy(keep_recent=10, compress_step=10), "Summary"),
    ]
    generate_report(results)
    print("\n" + "=" * 64 + "\n  ИТОГИ\n" + "=" * 64)
    for r in results:
        print(f"  {r['name']:<15} | {r['details_found']}/{r['details_total']} | "
              f"prompt {r['dialog_prompt'] + r['mgmt_prompt']:>6} | "
              f"mgmt-calls {r['mgmt_calls']:>2} | loc {r['loc']:>3}")