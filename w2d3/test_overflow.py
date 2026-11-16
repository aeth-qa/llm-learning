# test_overflow.py
from agent import SimpleAgent
from token_counter import count_messages_tokens

agent = SimpleAgent()

print("\n" + "=" * 60)
print("  ТЕСТ ПЕРЕПОЛНЕНИЯ КОНТЕКСТА")
print("=" * 60)

# Сбрасываем историю, чтобы тест был чистым
agent.reset()

# ~300K символов ≈ 120K токенов при коэффициенте ~2.5 симв./токен
huge = "Это очень длинный тестовый текст на русском языке. " * 20000

estimated = count_messages_tokens([{"role": "user", "content": huge}])
print(f"\nОтправляем сообщение ~{estimated} токенов")
print(f"Лимит deepseek-chat: 64 000 токенов")
print(f"Превышение: {estimated - 64000:+d} токенов\n")

try:
    answer = agent.run(huge)
    print(f"\n✅ Модель ответила: {answer[:200]}...")
except Exception as e:
    print(f"\n❌ Ошибка: {type(e).__name__}")
    print(f"   {str(e)[:500]}")

print("\n" + "=" * 60)
print("  Что осталось в out/history.json:")
print("=" * 60)
from storage import load_history
hist = load_history()
print(f"  Сообщений: {len(hist)}")
print(f"  Оценка токенов: ~{count_messages_tokens(hist)}")
print("\nЕсли история содержит огромное сообщение — следующий")
print("запуск main.py тоже упадёт. Это и есть баг для отчёта.")