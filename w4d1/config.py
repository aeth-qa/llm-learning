# config.py
from pathlib import Path
from openai import OpenAI

# 1. Читаем ключ. 
# Как и раньше, файл лежит на уровень выше папки w1d6.
key_file = Path(__file__).parent.parent / "key.deepseek"
API_KEY = key_file.read_text(encoding="utf-8").strip()

# 2. Создаём клиент (родной API DeepSeek)
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com",
    timeout=60.0, # 60 секунд с запасом
)

# 3. Модель, которую будем использовать
MODEL = "deepseek-chat"