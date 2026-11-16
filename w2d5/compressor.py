# compressor.py
from config import client, MODEL

COMPRESS_PROMPT = """Ты — система сжатия истории диалога. Твоя задача — сохранить ВСЕ 
фактические детали, чтобы ассистент мог позже на них ссылаться.

ПРАВИЛА:
- Сохраняй имена, числа, даты, суммы, бюджеты, сроки.
- Сохраняй принятые решения («решили использовать X»).
- Сохраняй ограничения («нельзя использовать Y»).
- Сохраняй контактных лиц и их роли.
- Не сохраняй приветствия, шутки, small talk.
- Пиши в форме кратких фактов: «Имя пользователя: Игорь», 
  «Бюджет: 250 000 ₽», «Срок: 15 декабря 2026».

Предыдущее резюме:
{previous_summary}

Новые сообщения для добавления:
{new_messages}

Составь обновлённое резюме (максимум 80 токенов). 
Выведи только текст резюме, без пояснений."""


def _format_messages(messages):
    lines = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content") or ""
        if m.get("tool_calls"):
            tools = ", ".join(tc["function"]["name"] for tc in m["tool_calls"])
            content = f"[вызов инструментов: {tools}]"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def compress(previous_summary, messages_to_compress):
    """Возвращает {"summary": str, "prompt_tokens": int, "completion_tokens": int}."""
    prompt = COMPRESS_PROMPT.format(
        previous_summary=previous_summary or "(пусто — это первое сжатие)",
        new_messages=_format_messages(messages_to_compress),
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return {
        "summary": response.choices[0].message.content.strip(),
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }