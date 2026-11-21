# extractors.py
import json
import re
from config import client, MODEL


EXTRACT_PROMPT = """Ты — система структурирования памяти ассистента.
Задача: обновить три хранилища, ТОЛЬКО если в новом сообщении
пользователя есть новая информация.

WORKING (эфемерное, меняется по ходу):
- Текущий фокус, этап работы
- Scope текущей итерации, что отложено
- Открытые вопросы, активные риски

LONG-TERM (финальное, согласованное):
- Имя, роль, компания пользователя
- Название проекта, описание
- Бюджет, сроки — финальные значения
- Технологические решения: БД, стек, архитектура
- Ограничения: цвета, часовой пояс, запреты

PROFILE (предпочтения пользователя в общении):
- Стиль ответа: «кратко» / «подробно» / «с примерами»
- Формат: «с кодом» / «без кода» / «таблицы» / «списки»
- Тон: «формально» / «неформально» / «дружелюбно» / «сухо»
- Ограничения стиля: «без markdown», «без эмодзи» и т.п.
Меняется ТОЛЬКО если пользователь явно высказал или изменил предпочтение.

ПРАВИЛА:
- Не дублируй между слоями (факт о задаче → long, предпочтение стиля → profile).
- Если значение изменилось — замени, не копи старые.
- Small talk и вопросы — не сохраняй.
- Если новой информации нет — верни хранилища без изменений.

Текущий WORKING: {working}
Текущий LONG: {long}
Текущий PROFILE: {profile}

Новое сообщение пользователя:
{message}

Верни ТОЛЬКО валидный JSON без markdown:
{{"working": {{...}}, "long": {{...}}, "profile": {{...}}}}
"""


def extract(message, current_working, current_long, current_profile):
    prompt = EXTRACT_PROMPT.format(
        working=json.dumps(current_working, ensure_ascii=False),
        long=json.dumps(current_long, ensure_ascii=False),
        profile=json.dumps(current_profile, ensure_ascii=False),
        message=message,
    )
    response = client.chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": prompt}]
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
        return current_working, current_long, current_profile, usage

    nw = data.get("working") if isinstance(data.get("working"), dict) else current_working
    nl = data.get("long") if isinstance(data.get("long"), dict) else current_long
    np_ = data.get("profile") if isinstance(data.get("profile"), dict) else current_profile
    return nw, nl, np_, usage
