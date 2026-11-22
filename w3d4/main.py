# main.py
from pathlib import Path

from agent import SimpleAgent
from agent import clean_for_console
from memory import MemoryModel
from token_counter import estimate_cost


STATE = Path("out") / "memory_state.json"


def show_memory(agent):
    from agent import SYSTEM_PROMPT
    b = agent.memory.token_breakdown(SYSTEM_PROMPT)
    print(f"\n─── Память ───")
    print(f"SHORT:   {len(agent.memory.short)} сообщений (~{b['short']} ток.)")
    print(f"WORKING: {len(agent.memory.working)} записей (~{b['working']} ток.)")
    for k, v in agent.memory.working.items():
        print(f"  • {k}: {v}")
    print(f"LONG:    {len(agent.memory.long)} записей (~{b['long']} ток.)")
    for k, v in agent.memory.long.items():
        print(f"  • {k}: {v}")
    print(f"ИТОГО промпт: ~{b['total']} ток.")


def show_stats(agent):
    s, e = agent.session_stats, agent.extraction_stats
    tp = s["dialog_prompt_tokens"] + e["prompt_tokens"]
    tc = s["dialog_completion_tokens"] + e["completion_tokens"]
    print(f"\n─── Статистика ───")
    print(f"Диалоговых вызовов:  {s['dialog_calls']}")
    print(f"Вызовов экстрактора: {e['calls']}")
    print(f"Prompt (диалог):     {s['dialog_prompt_tokens']}")
    print(f"Prompt (экстрактор): {e['prompt_tokens']}")
    print(f"Completion всего:    {tc}")
    print(f"Стоимость (оценка):  ${estimate_cost(tp, tc):.4f}")


def main():
    print("=" * 64)
    print("  SimpleAgent — модель памяти (short / working / long)")
    print("  Команды: выход | память | статистика")
    print("           очистить short|working|long|всё")
    print("=" * 64)

    if STATE.exists():
        memory = MemoryModel.load(STATE)
        print(f"📂 Загружено из {STATE}")
    else:
        memory = MemoryModel(short_window=10)

    agent = SimpleAgent(memory)

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
        if low in ("память", "memory"):
            show_memory(agent); continue
        if low in ("статистика", "stats"):
            show_stats(agent); continue
        if low.startswith("очистить"):
            parts = low.split()
            t = parts[1] if len(parts) > 1 else "всё"
            if t == "short":   agent.memory.clear_short();    print("🧹 short")
            elif t == "working": agent.memory.clear_working(); print("🧹 working")
            elif t == "long":   agent.memory.clear_long();    print("🧹 long")
            else:               agent.memory.clear_all();     print("🧹 всё")
            agent.memory.save(STATE)
            continue
        if low in ("профиль", "profile"):
            if agent.memory.profile:
                from token_counter import count_tokens
                import json as _json
                txt = _json.dumps(agent.memory.profile, ensure_ascii=False, indent=2)
                print(f"\n─── Профиль ({count_tokens(txt)} ток.) ───")
                print(txt)
                print("─────────────────────────────\n")
            else:
                print("\n[Профиль пуст.]\n")
            continue
                if low in ("состояние", "state"):
            from task_state import describe
            print(f"\n─── Состояние задачи ───")
            print(describe())
            print("────────────────────────\n")
            continue
        if low in ("пауза", "pause"):
            from task_state import pause
            print(pause("вручную"))
            continue
        if low in ("продолжить", "resume"):
            from task_state import resume
            print(resume())
            continue
        if low in ("сброс-задачи", "task-reset"):
            from task_state import reset
            reset()
            print("🧹 Состояние задачи сброшено в planning.")
            continue
        print("\nАгент думает...")
        answer = agent.run(q)
        if answer is not None:
            print(f"\nАгент: {clean_for_console(answer)}")
        
        agent.memory.save(STATE)


if __name__ == "__main__":
    main()