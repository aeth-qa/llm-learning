# main.py
from agent import SimpleAgent
from token_counter import count_messages_tokens, estimate_cost


def show_stats(agent):
    s = agent.session_stats
    print(f"\n─── Статистика сессии ───")
    print(f"Вызовов API:        {s['calls']}")
    print(f"Prompt-токенов:     {s['prompt_tokens']}")
    print(f"Completion-токенов: {s['completion_tokens']}")
    print(f"Всего токенов:      {s['total_tokens']}")
    est_cost = estimate_cost(s["prompt_tokens"], s["completion_tokens"])
    print(f"Оценка стоимости:   ${est_cost:.4f}")
    print(f"Сообщений в истории:{len(agent.messages)}")
    print(f"Оценка токенов:     ~{count_messages_tokens(agent.messages)}")


def demo_overflow(agent):
    repeat = 100000
    huge = "Это очень длинный тестовый текст на русском языке. " * repeat
    print(f"\n[ДЕМО] Готовим сообщение: {repeat} повторов, "
          f"~{len(huge)//1024} КБ.")
    print(f"[ДЕМО] Отправляем в модель. Ожидаем 400 Bad Request.\n")
    answer = agent.run(huge)
    if answer is None:
        print("[ДЕМО] Агент пережил ошибку. История чистая, можно продолжать.\n")
    else:
        print(f"\nАгент: {answer[:200]}")


def main():
    print("=" * 55)
    print("  SimpleAgent CLI (с сохранением контекста)")
    print("  'выход' — выйти, 'очистить' — сбросить историю,")
    print("  'статистика' — токены и стоимость,")
    print("  'демо-переполнение' — сценарий с 400")
    print("=" * 55)

    agent = SimpleAgent()

    while True:
        try:
            query = input("\nВы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо свидания!")
            break

        if not query:
            continue
        if query.lower() in ("выход", "exit", "quit"):
            print("До свидания!")
            break
        if query.lower() in ("очистить", "clear", "reset"):
            agent.reset()
            continue
        if query.lower() in ("статистика", "stats"):
            show_stats(agent)
            continue
        if query.lower() in ("демо-переполнение", "demo-overflow", "demo"):
            demo_overflow(agent)
            continue

        print("\nАгент думает...")
        try:
            answer = agent.run(query)
            if answer is not None:
                print(f"\nАгент: {answer}")
            # Если None — агент уже напечатал сообщение об ошибке
        except Exception as e:
            print(f"\n[Ошибка] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()