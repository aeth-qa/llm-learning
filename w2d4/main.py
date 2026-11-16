# main.py
from agent import SimpleAgent
from token_counter import count_messages_tokens, estimate_cost


def show_stats(agent):
    s = agent.session_stats
    c = agent.compression_stats
    print(f"\n─── Статистика сессии ───")
    print(f"Вызовов API:            {s['calls']}")
    print(f"Prompt-токенов (диалог): {s['prompt_tokens']}")
    print(f"Completion (диалог):     {s['completion_tokens']}")
    print(f"Сжатий:                  {c['calls']}")
    print(f"Prompt-токенов (сжатие): {c['prompt_tokens']}")
    print(f"Completion (сжатие):     {c['completion_tokens']}")
    total_prompt = s["prompt_tokens"] + c["prompt_tokens"]
    total_completion = s["completion_tokens"] + c["completion_tokens"]
    cost = estimate_cost(total_prompt, total_completion)
    print(f"Всего prompt:            {total_prompt}")
    print(f"Стоимость (оценка):      ${cost:.4f}")
    print(f"Hot-история:             {len(agent.history)} сообщений")
    print(f"Summary:                 {'есть, ' + str(len(agent.summary)) + ' симв.' if agent.summary else 'нет'}")
    print(f"Оценка токенов сейчас:   ~{count_messages_tokens(agent._build_api_messages())}")


def show_summary(agent):
    if not agent.summary:
        print("\n[Summary пуст — пока ничего не сжато.]\n")
        return
    print("\n─── Текущее summary ───")
    print(agent.summary)
    print("───────────────────────\n")


def demo_overflow(agent):
    repeat = 100000
    huge = "Это очень длинный тестовый текст на русском языке. " * repeat
    print(f"\n[ДЕМО] Отправляем ~{len(huge)//1024} КБ текста. Ожидаем 400.\n")
    answer = agent.run(huge)
    if answer is None:
        print("[ДЕМО] Агент пережил ошибку. История откатана.\n")
    else:
        print(f"\nАгент: {answer[:200]}")


def main():
    print("=" * 62)
    print("  SimpleAgent CLI (со сжатием контекста)")
    print("  'выход'    'очистить'    'статистика'")
    print("  'резюме'   'демо-переполнение'")
    print("=" * 62)

    agent = SimpleAgent(use_compression=True)

    while True:
        try:
            query = input("\nВы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо свидания!")
            break

        if not query:
            continue
        low = query.lower()
        if low in ("выход", "exit", "quit"):
            print("До свидания!")
            break
        if low in ("очистить", "clear", "reset"):
            agent.reset()
            continue
        if low in ("статистика", "stats"):
            show_stats(agent)
            continue
        if low in ("резюме", "summary"):
            show_summary(agent)
            continue
        if low in ("демо-переполнение", "demo-overflow", "demo"):
            demo_overflow(agent)
            continue

        print("\nАгент думает...")
        try:
            answer = agent.run(query)
            if answer is not None:
                print(f"\nАгент: {answer}")
        except Exception as e:
            print(f"\n[Ошибка] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()