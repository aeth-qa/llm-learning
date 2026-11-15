# main.py
from agent import SimpleAgent

def main():
    print("=" * 55)
    print("  SimpleAgent CLI")
    print("  Введите 'выход' для завершения")
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

        print("\nАгент думает...")
        try:
            answer = agent.run(query)
            print(f"\nАгент: {answer}")
        except Exception as e:
            print(f"\n[Ошибка] {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()