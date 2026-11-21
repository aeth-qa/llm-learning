# extractors.py
import json
import re
from config import client, MODEL


EXTRACT_PROMPT = """Ты — система структурирования памяти ассистента.
Задача: обновить два хранилища, ТОЛЬКО если в новом сообщении
пользователя есть новая фактическая информация.

WORKING (эфемерное, может меняться по ходу):
- Текущий фокус, текущий этап работы
- Scope текущей итерации/MVP (что делаем сейчас, что отложили)
- Открытые вопросы
- Активные риски

LONG-TERM (финальное, согласованное):
- Имя, роль, компания пользователя
- Название проекта
- Бюджет, сроки — финальные значения
- Технологические решения: БД, стек, архитектура
- Ограничения и предпочтения: цвета, часовой пояс, запреты

ПРАВИЛА:
- НЕ дублируй между слоями (если факт уже в LONG — не копируй в WORKING).
- Если факт обновился — замени значение, не копи старые.
- Small talk, приветствия, вопросы — НЕ сохраняй.
- Ключи короткие, на русском. Значения — строки.
- Если новой информации нет — верни оба хранилища без изменений.

Текущий WORKING: {working}
Текущий LONG: {long}

Новое сообщение пользователя:
{message}

Верни ТОЛЬКО валидный JSON без markdown:
{{"working": {{...}}, "long": {{...}}}}
"""


def extract(message, current_working, current_long):
    """Возвращает (new_working, new_long, usage)."""
    prompt = EXTRACT_PROMPT.format(
        working=json.dumps(current_working, ensure_ascii=False),
        long=json.dumps(current_long, ensure_ascii=False),
        message=message,
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"    ⚠️  Экстрактор вернул не JSON: {e}")
        return current_working, current_long, usage

    new_working = data.get("working") if isinstance(data.get("working"), dict) else current_working
    new_long = data.get("long") if isinstance(data.get("long"), dict) else current_long
    return new_working, new_long, usage