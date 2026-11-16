# main.py
import json
from pathlib import Path

from agent import SimpleAgent
from strategies import (
    SlidingWindowStrategy, StickyFactsStrategy, SummaryStrategy,
)
from token_counter import estimate_cost


def choose_strategy():
    print("\nВыберите стратегию управления контекстом:")
    print("  1. Sliding Window (последние 10 сообщений)")
    print("  2. Sticky Facts (facts + последние 10 сообщений)")
    print("  3. Summary (сжатие + последние 10 сообщений)")
    while True:
        c = input("Ваш выбор [1/2/3]: ").strip()
        if c == "1": return SlidingWindowStrategy()
        if c == "2": return StickyFactsStrategy()
        if c == "3": return SummaryStrategy()


def show_stats(agent):
    s = agent.session_stats
    m = agent.strategy.stats
    tp = s["dialog_prompt_tokens"] + m["management_prompt_tokens"]
    tc = s["dialog_completion_tokens"] + m["management_completion_tokens"]
    print(f"\n─── Статистика ───")
    print(f"Стратегия:            {agent.strategy.name}")
    print(f"Диалоговых вызовов:   {s['dialog_calls']}")
    print(f"Prompt (диалог):      {s['dialog_prompt_tokens']}")
    print(f"Completion (диалог):  {s['dialog_completion_tokens']}")
    print(f"Вызовов управления:   {m['management_calls']}")
    print(f"Prompt (управление):  {m['management_prompt_tokens']}")
    print(f"Completion (упр.):    {m['management_completion_tokens']}")
    print(f"Всего prompt:         {tp}")
    print(f"Стоимость (оценка):   ${estimate_cost(tp, tc):.4f}")

    st = agent.strategy.state()
    if "facts" in st:
        print(f"Facts ({len(st['facts'])}):")
        for k, v in st["facts"].items():
            print(f"  • {k}: {v}")
    if "summary" in st and st["summary"]:
        print(f"Summary: {st['summary'][:180]}...")
    if "messages" in st:
        print(f"Hot-сообщений:        {len(st['messages'])}")


def main():
    print("=" * 64)
    print("  SimpleAgent CLI — выбор стратегии контекста")
    print("  Команды: выход | очистить | статистика")
    print("           checkpoint <имя> | загрузить <имя> | сменить")
    print("=" * 64)

    strategy = choose_strategy()
    agent = SimpleAgent(strategy)

    while True:
        try:
            q = input("\nВы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо свидания!")
            break
        if not q:
            continue
        low = q.lower()

        if low in ("выход", "exit", "quit"):
            print("До свидания!")
            break
        if low == "очистить":
            agent = SimpleAgent(choose_strategy())
            print("🧹 Новый агент, чистое состояние.")
            continue
        if low == "статистика":
            show_stats(agent)
            continue
        if low.startswith("checkpoint "):
            name = q.split(maxsplit=1)[1]
            path = Path("out") / "checkpoints" / f"{name}.json"
            agent.save_checkpoint(path)
            print(f"💾 Сохранено: {path}")
            continue
        if low.startswith("загрузить "):
            name = q.split(maxsplit=1)[1]
            path = Path("out") / "checkpoints" / f"{name}.json"
            if not path.exists():
                print(f"❌ Не найден: {path}")
                continue
            agent.load_checkpoint(path)
            print(f"📂 Загружено: {path}")
            continue
        if low == "сменить":
            strategy = choose_strategy()
            agent = SimpleAgent(strategy)
            print("🔄 Стратегия сменена, состояние сброшено.")
            continue

        print("\nАгент думает...")
        try:
            answer = agent.run(q)
            if answer is not None:
                print(f"\nАгент: {answer}")
        except Exception as e:
            print(f"\n[Ошибка] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()