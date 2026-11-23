# extractors.py
import json
import re
from config import client, MODEL


EXTRACT_PROMPT = """Ты — система структурирования памяти ассистента.
Задача: извлечь из нового сообщения пользователя ТОЛЬКО новую или изменившуюся информацию.

WORKING (полное состояние, эфемерное):
- Текущий фокус, этап работы
- Scope текущей итерации, что отложено
- Открытые вопросы, активные риски
Верни ПОЛНЫЙ словарь (можно с изменениями, можно тот же, что был).

PROFILE (предпочтения пользователя):
- Стиль ответа, формат, тон
Верни ПОЛНЫЙ словарь.

LONG_UPDATES (только дельты!):
- Верни ТОЛЬКО ключи, которые появились или изменились.
- Если факт изменился — верни новое значение.
- Если факт просто упомянут без изменений — НЕ включай.
- Для сроков, бюджетов, версий, статусов — верни новое значение (одно, не список).

ПРАВИЛА ДЛЯ РЕШЕНИЙ (важно!):
- Любое принятое решение (например, «нанимаем DevOps», «добавляем pg_cron», 
  «выбрали Docker») кладётся в ЕДИНЫЙ ключ "решения" как ЭЛЕМЕНТ МАССИВА.
- НЕ создавай отдельные ключи вроде "devops", "pg_cron", "docker", 
  "решение_devops" — они все элементы одного списка "решения".
- Пример правильной дельты: {{"решения": ["нанимаем DevOps с первого дня"]}}
- Если решений несколько за раз — верни массив с несколькими элементами.

ПРАВИЛА (общие):
- Не дублируй между слоями.
- Small talk и вопросы — не сохраняй.
- Если новой информации нет — верни пустые дельты.

Текущий WORKING: {working}
Текущий LONG: {long}
Текущий PROFILE: {profile}

Новое сообщение пользователя:
{message}

Верни ТОЛЬКО валидный JSON без markdown:
{{"working": {{...}}, "long_updates": {{...}}, "profile": {{...}}}}
"""


def extract(message, current_working, current_long_flat, current_profile):
    prompt = EXTRACT_PROMPT.format(
        working=json.dumps(current_working, ensure_ascii=False),
        long=json.dumps(current_long_flat, ensure_ascii=False),
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
        return current_working, {}, current_profile, usage

    nw = data.get("working") if isinstance(data.get("working"), dict) else current_working
    lu = data.get("long_updates") if isinstance(data.get("long_updates"), dict) else {}
    np_ = data.get("profile") if isinstance(data.get("profile"), dict) else current_profile
    return nw, lu, np_, usage