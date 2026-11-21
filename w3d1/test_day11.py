# test_day11.py
import json
from datetime import datetime
from pathlib import Path

from agent import SimpleAgent
from agent import clean_for_console

from memory import MemoryModel


OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)
SNAPSHOT = OUT_DIR / "memory_snapshot.json"
REPORT = OUT_DIR / "day11_report.md"


DIALOGUE = [
    # 1–7: факты с уникальными значениями
    "Привет, меня зовут Игорь Владимирович. Будем работать над проектом.",
    "Проект называется «Кофе-тайм» — это приложение для заказа кофе.",
    "Бюджет — 247 300 рублей. Это финальная сумма, больше не будет.",
    "Срок жёсткий: сдать нужно до 17 декабря 2026.",
    "База данных — PostgreSQL 16 с расширением pg_cron. MongoDB не подходит.",
    "Бренд-цвет — тёмно-зелёный, hex #3A9F61. Логотип будет на нём.",
    "Команда в Москве, работаем по МСК (UTC+3).",
    # 8: MVP scope
    "Важно: в этой итерации MVP должен включать только заказ и оплату. "
    "Доставку и лояльность — во вторую версию.",
    # 9–13: обсуждение без рекапа
    "Какие риски ты видишь?",
    "Что по архитектуре посоветуешь?",
    "Как лучше тестировать?",
    "Реально уложиться в такие сроки?",
    "Как монетизировать будем?",
    # 14–23: 10 дистракторов про найм
    "Теперь обсудим найм. Кого нам не хватает?",
    "А бэкенд-разработчик нужен?",
    "Фронтендер отдельно или fullstack?",
    "Сколько QA-инженеров достаточно?",
    "DevOps нужен с первого дня?",
    "Продакт-менеджер — критичен?",
    "Аналитик данных пригодится?",
    "Дизайнер — когда подключать?",
    "Нанимаем in-house или аутсорс?",
    "Какие грейды нужны на старте?",
    # 24: последняя тема
    "Отлично. Сейчас главное — тестирование и найм. Двигаемся.",
]

PROBES = [
    {"layer": "long", "name": "Имя", "q": "Как меня зовут?",
     "expect": ["игор", "владимирович"]},
    {"layer": "long", "name": "Проект", "q": "Как называется проект?",
     "expect": ["кофе-тайм", "кофе тайм"]},
    {"layer": "long", "name": "Бюджет", "q": "Какой у нас бюджет?",
     "expect": ["247 300", "247300"]},
    {"layer": "long", "name": "Срок", "q": "Какой срок сдачи?",
     "expect": ["17 декабря", "17.12", "декабря 2026"]},
    {"layer": "long", "name": "База", "q": "Какую базу данных выбрали?",
     "expect": ["postgresql 16", "pg_cron", "postgresql"]},
    {"layer": "long", "name": "Цвет", "q": "Какой цвет бренда?",
     "expect": ["3a9f61", "тёмно-зелёный", "темно-зеленый"]},
    {"layer": "long", "name": "Пояс", "q": "Какой часовой пояс у команды?",
     "expect": ["мск", "utc+3", "московск"]},
    {"layer": "working", "name": "MVP", "q": "Что входит в MVP этой итерации?",
     "expect": ["заказ", "оплат"]},
    {"layer": "short", "name": "Последняя тема",
     "q": "Коротко назови последнюю тему, которую мы обсуждали до этого вопроса.",
     "expect": ["тестирован", "найм"]},
]

def strict_probe(question):
    return (
        question
        + "\n\nВАЖНО: если в доступной информации нет точного ответа, "
          "ответь ровно «НЕТ ДАННЫХ». Не угадывай."
    )

def check(answer, expect):
    if not answer:
        return False
    low = answer.lower()
    # Явный отказ — сразу False, никаких совпадений в тексте не считаем
    refusal_markers = ["нет данных", "не знаю", "не уверен",
                       "не могу определить", "неизвестно"]
    if any(m in low for m in refusal_markers):
        return False
    return any(e.lower() in low for e in expect)


def run_dialogue():
    print("=" * 64)
    print("  ФАЗА 1: диалог, наполняем память")
    print("=" * 64)
    memory = MemoryModel(short_window=10)
    agent = SimpleAgent(memory)
    for i, msg in enumerate(DIALOGUE, 1):
        agent.run(msg)
        if i % 4 == 0 or i == len(DIALOGUE):
            print(f"  {i:>2}/{len(DIALOGUE)} | short={len(memory.short):>2} "
                  f"| working={len(memory.working):>2} | long={len(memory.long):>2}")
    memory.save(SNAPSHOT)
    return agent


def run_probes(baseline, clear_layer=None):
    results = {}
    for probe in PROBES:
        mem = MemoryModel.from_dict(baseline)
        if clear_layer == "short":    mem.clear_short()
        if clear_layer == "working":  mem.clear_working()
        if clear_layer == "long":     mem.clear_long()
        agent = SimpleAgent(mem)
        answer = agent.run(strict_probe(probe["q"]), extract=False) or ""
        results[probe["name"]] = {
            "answer": answer[:200],
            "ok": check(answer, probe["expect"]),
            "layer": probe["layer"],
        }
    return results


def summarize(results):
    by_layer = {"long": [0, 0], "working": [0, 0], "short": [0, 0]}
    for r in results.values():
        by_layer[r["layer"]][1] += 1
        if r["ok"]:
            by_layer[r["layer"]][0] += 1
    return {"by_layer": by_layer,
            "total_ok": sum(v[0] for v in by_layer.values()),
            "total": sum(v[1] for v in by_layer.values())}


def generate_report(agent, breakdown, scenarios):
    L = ["# День 11. Модель памяти ассистента\n\n",
         f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n",
         f"Диалог: {len(DIALOGUE)} реплик. Пробы: {len(PROBES)} "
         f"(7 long + 1 working + 1 short).\n\n"]

    L.append("## Что попало в каждый слой\n\n")
    L.append(f"**Short** — {len(agent.memory.short)} сообщений "
             f"(окно = {agent.memory.short_window}).\n\n")

    L.append(f"**Working** — {len(agent.memory.working)} записей:\n\n")
    if agent.memory.working:
        L.append("```\n" + json.dumps(agent.memory.working, ensure_ascii=False, indent=2) + "\n```\n\n")
    else:
        L.append("_(пусто)_\n\n")

    L.append(f"**Long-term** — {len(agent.memory.long)} записей:\n\n")
    if agent.memory.long:
        L.append("```\n" + json.dumps(agent.memory.long, ensure_ascii=False, indent=2) + "\n```\n\n")
    else:
        L.append("_(пусто)_\n\n")

    L.append("## Вклад слоёв в промпт (токены)\n\n")
    L.append("| Слой | Токенов |\n|---|---:|\n")
    for layer in ["system", "long", "working", "short"]:
        L.append(f"| {layer} | {breakdown[layer]} |\n")
    L.append(f"| **Итого** | **{breakdown['total']}** |\n\n")

    L.append("## Результаты очистки слоёв\n\n")
    L.append("| Сценарий | Long (7) | Working (1) | Short (1) | Итого |\n")
    L.append("|---|---:|---:|---:|---:|\n")
    for name, s in scenarios.items():
        bl = s["by_layer"]
        L.append(f"| {name} | {bl['long'][0]}/{bl['long'][1]} | "
                 f"{bl['working'][0]}/{bl['working'][1]} | "
                 f"{bl['short'][0]}/{bl['short'][1]} | "
                 f"{s['total_ok']}/{s['total']} |\n")

    REPORT.write_text("".join(L), encoding="utf-8")
    print(f"\n📄 {REPORT}")


if __name__ == "__main__":
    agent = run_dialogue()
    baseline = agent.memory.to_dict()

    from agent import SYSTEM_PROMPT
    breakdown = agent.memory.token_breakdown(SYSTEM_PROMPT)

    print("\n" + "=" * 64)
    print("  ФАЗА 2: вклад слоёв")
    print("=" * 64)
    for k in ["system", "long", "working", "short", "total"]:
        print(f"  {k:<8}: {breakdown[k]:>5} ток.")
    print(f"\n  WORKING: {json.dumps(agent.memory.working, ensure_ascii=False)}")
    print(f"  LONG:    {json.dumps(agent.memory.long, ensure_ascii=False)}")

    print("\n" + "=" * 64)
    print("  ФАЗА 3: пробы + очистка слоёв")
    print("=" * 64)

    scenarios = {}
    for name, layer in [
        ("Все слои (baseline)", None),
        ("Без short", "short"),
        ("Без working", "working"),
        ("Без long", "long"),
    ]:
        print(f"\n  → {name}")
        results = run_probes(baseline, clear_layer=layer)
        s = summarize(results)
        scenarios[name] = s
        for pname, r in results.items():
            print(f"    [{r['layer']:<7}] {pname:<16} "
            f"{'✅' if r['ok'] else '❌'}  "
            f"{clean_for_console(r['answer'])[:70]}")

    generate_report(agent, breakdown, scenarios)

    print("\n" + "=" * 64)
    print("  ИТОГИ")
    print("=" * 64)
    for name, s in scenarios.items():
        bl = s["by_layer"]
        print(f"  {name:<22} | Long {bl['long'][0]}/{bl['long'][1]} "
              f"| Work {bl['working'][0]}/{bl['working'][1]} "
              f"| Short {bl['short'][0]}/{bl['short'][1]} "
              f"| Всего {s['total_ok']}/{s['total']}")