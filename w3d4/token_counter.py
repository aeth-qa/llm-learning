# token_counter.py
import json
import sys
import tiktoken

# ─── Загружаем словарь. Если не получается — завершаемся с понятным сообщением ─
try:
    _encoder = tiktoken.get_encoding("o200k_base")
except Exception as e:
    print("\n" + "=" * 62)
    print("❌ Не удалось загрузить словарь токенов tiktoken.")
    print(f"   Причина: {type(e).__name__}: {str(e)[:200]}")
    print()
    print("   Это происходит при первом запуске: библиотека скачивает")
    print("   файл словаря с серверов OpenAI. Из некоторых регионов")
    print("   этот сервер (openaipublic.blob.core.windows.net) недоступен.")
    print()
    print("   Что делать:")
    print("   1. Включите VPN так, чтобы через него шёл трафик Python.")
    print("   2. Запустите скрипт ещё раз — словарь закэшируется.")
    print("   3. После этого VPN можно выключить, tiktoken будет")
    print("      работать из кэша без сети.")
    print("=" * 62 + "\n")
    sys.exit(1)

# ─── Кэшируем overhead от схемы инструментов (считается один раз) ───────────
# Импорт tools безопасен: tools.py не импортирует ничего из нашего проекта.
from tools import TOOLS_SCHEMA

_TOOLS_OVERHEAD = len(_encoder.encode(json.dumps(TOOLS_SCHEMA, ensure_ascii=False)))

# Служебные токены шаблона чата (<|im_start|>, <|im_end|> и т.п.).
# Точное значение зависит от провайдера; 80 — разумная консервативная оценка.
_CHAT_TEMPLATE_OVERHEAD = 80

# ─── Цены DeepSeek (актуальные — на platform.deepseek.com/pricing) ─────────
PRICE_IN_PER_1M = 0.27
PRICE_OUT_PER_1M = 1.10


def count_tokens(text):
    """Точный подсчёт токенов в строке."""
    if not text:
        return 0
    return len(_encoder.encode(text))


def count_messages_tokens(messages, include_tools=True):
    """Точный подсчёт токенов в списке messages.

    include_tools=True — включает overhead от TOOLS_SCHEMA,
    который уходит в модель с КАЖДЫМ запросом (если tools переданы).
    Поставьте False, если считаете запрос без инструментов.
    """
    total = _CHAT_TEMPLATE_OVERHEAD
    if include_tools:
        total += _TOOLS_OVERHEAD

    for m in messages:
        total += 4  # служебный overhead на сообщение (роль, разделители)
        content = m.get("content")
        if content:
            total += count_tokens(content)
        for tc in m.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            total += count_tokens(fn.get("name", ""))
            total += count_tokens(fn.get("arguments", ""))

    return total


def estimate_cost(prompt_tokens, completion_tokens):
    """Оценка стоимости в долларах по тарифам DeepSeek."""
    return (
        prompt_tokens / 1_000_000 * PRICE_IN_PER_1M
        + completion_tokens / 1_000_000 * PRICE_OUT_PER_1M
    )