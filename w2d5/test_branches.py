# test_branches.py
import json
from pathlib import Path

from agent import SimpleAgent
from strategies import StickyFactsStrategy


BRANCHES_DIR = Path(__file__).parent / "out" / "branches"
BRANCHES_DIR.mkdir(parents=True, exist_ok=True)


def show_facts(agent, label):
    print(f"  [{label}] facts = {json.dumps(agent.strategy.facts, ensure_ascii=False)}")


def main():
    print("=" * 64)
    print("  ШАГ 1: Общий диалог (3 реплики)")
    print("=" * 64)
    agent = SimpleAgent(StickyFactsStrategy(keep_recent=10))
    agent.run("Привет, я Игорь. Делаем приложение «Кофе-тайм».")
    agent.run("Бюджет — 250 000 рублей. Срок — 15 декабря 2026.")
    agent.run("База данных — PostgreSQL, потому что нужны транзакции.")
    show_facts(agent, "после общего диалога")

    cp = BRANCHES_DIR / "checkpoint.json"
    agent.save_checkpoint(cp)
    print(f"\n💾 Checkpoint: {cp}")

    print("\n" + "=" * 64)
    print("  ШАГ 2: Ветка A — бюджет +50 000")
    print("=" * 64)
    a = SimpleAgent(StickyFactsStrategy(keep_recent=10))
    a.load_checkpoint(cp)
    show_facts(a, "A до изменения")
    a.run("Слушай, я нашёл ещё 50 000. Теперь бюджет 300 000 рублей.")
    show_facts(a, "A после изменения")
    a.save_checkpoint(BRANCHES_DIR / "branch_a.json")

    print("\n" + "=" * 64)
    print("  ШАГ 3: Ветка B — срок сдвигается")
    print("=" * 64)
    b = SimpleAgent(StickyFactsStrategy(keep_recent=10))
    b.load_checkpoint(cp)
    show_facts(b, "B до изменения")
    b.run("Срок сдвигается: сдаём не 15 декабря, а 20 января 2027.")
    show_facts(b, "B после изменения")
    b.save_checkpoint(BRANCHES_DIR / "branch_b.json")

    print("\n" + "=" * 64)
    print("  ШАГ 4: Переключаемся между ветками")
    print("=" * 64)

    a2 = SimpleAgent(StickyFactsStrategy(keep_recent=10))
    a2.load_checkpoint(BRANCHES_DIR / "branch_a.json")
    print("\n[Ветка A] «Какой бюджет?»")
    print("Ответ:", a2.run("Напомни, какой у нас бюджет?"))
    print("[Ветка A] «Какой срок?»")
    print("Ответ:", a2.run("И какой срок сдачи?"))

    b2 = SimpleAgent(StickyFactsStrategy(keep_recent=10))
    b2.load_checkpoint(BRANCHES_DIR / "branch_b.json")
    print("\n[Ветка B] «Какой бюджет?»")
    print("Ответ:", b2.run("Напомни, какой у нас бюджет?"))
    print("[Ветка B] «Какой срок?»")
    print("Ответ:", b2.run("И какой срок сдачи?"))


if __name__ == "__main__":
    main()