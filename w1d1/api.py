from pathlib import Path
from openai import OpenAI

# 1. Читаем ключ из файла "key" рядом со скриптом
key_file = Path(__file__).parent.parent / "key"
api_key = key_file.read_text(encoding="utf-8").strip()

# 2. Клиент DeepSeek
client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

# 3. Ждём ввода с клавиатуры
question = input("Введите вопрос: ")

# 4. Отправляем запрос
print("\nДумаю...\n")
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "Ты — полезный ассистент."},
        {"role": "user", "content": question}
    ],
    stream=False
)

# 5. Выводим ответ
print("Ответ от DeepSeek:\n")
print(response.choices[0].message.content)