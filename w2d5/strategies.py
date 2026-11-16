# strategies.py
"""
Три стратегии управления контекстом.

Общий интерфейс (ContextStrategy):
  add_message(role, content, **extra) — добавить сообщение
  get_api_messages(system_prompt)      — вернуть messages для API
  finalize_turn()                      — вызвать после полного хода (опционально)
  state() / load_state(state)          — сериализация для checkpoint
  stats                                — счётчики "управляющих" вызовов
"""
import json
import re
from abc import ABC, abstractmethod
from config import client, MODEL


SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом. "
    "Не используй markdown-разметку: без **, ##, ```, без таблиц."
)


def safe_trim_messages(messages, keep_recent):
    """Последние keep_recent сообщений, но без разрыва пары tool_call ↔ tool."""
    if len(messages) <= keep_recent:
        return list(messages)
    trimmed = list(messages[-keep_recent:])
    while trimmed and (
        trimmed[0].get("role") == "tool"
        or (trimmed[0].get("role") == "assistant" and trimmed[0].get("tool_calls"))
    ):
        trimmed = trimmed[1:]
    return trimmed


class ContextStrategy(ABC):
    name = "abstract"

    def __init__(self):
        self.stats = {
            "management_calls": 0,
            "management_prompt_tokens": 0,
            "management_completion_tokens": 0,
        }

    @abstractmethod
    def add_message(self, role, content, **extra):
        ...

    @abstractmethod
    def get_api_messages(self, system_prompt):
        ...

    def finalize_turn(self):
        pass

    def state(self):
        return {}

    def load_state(self, state):
        pass


# ─── Стратегия 1: Sliding Window ─────────────────────────────────────────────
class SlidingWindowStrategy(ContextStrategy):
    name = "Sliding Window"

    def __init__(self, keep_recent=10):
        super().__init__()
        self.keep_recent = keep_recent
        self.messages = []

    def add_message(self, role, content, **extra):
        msg = {"role": role}
        if content is not None:
            msg["content"] = content
        msg.update(extra)
        self.messages.append(msg)
        if len(self.messages) > self.keep_recent:
            self.messages = safe_trim_messages(self.messages, self.keep_recent)

    def get_api_messages(self, system_prompt):
        return [{"role": "system", "content": system_prompt}] + self.messages

    def state(self):
        return {"messages": self.messages, "keep_recent": self.keep_recent}

    def load_state(self, state):
        self.messages = state.get("messages", [])
        self.keep_recent = state.get("keep_recent", self.keep_recent)


# ─── Стратегия 2: Sticky Facts ───────────────────────────────────────────────
class StickyFactsStrategy(ContextStrategy):
    name = "Sticky Facts"

    FACT_EXTRACT_PROMPT = """Ты — экстрактор фактов из диалога с пользователем.
На вход: текущие facts (JSON) и новое сообщение пользователя.
Задача: вернуть ОБНОВЛЁННЫЙ JSON с фактами.

Правила:
- Сохраняй конкретные данные: имя, названия, числа, суммы, сроки, ограничения, решения, предпочтения.
- Если факт изменился — замени значение.
- Если новой фактической информации нет — верни текущие facts без изменений.
- Не сохраняй small talk, приветствия, общие рассуждения, вопросы.
- Ключи короткие, на русском. Значения — строки.
- Формат: {{"ключ": "значение", ...}}

Текущие facts:
{facts}

Новое сообщение пользователя:
{user_message}

Верни ТОЛЬКО валидный JSON, без markdown и пояснений."""

    def __init__(self, keep_recent=10):
        super().__init__()
        self.keep_recent = keep_recent
        self.messages = []
        self.facts = {}

    def add_message(self, role, content, **extra):
        msg = {"role": role}
        if content is not None:
            msg["content"] = content
        msg.update(extra)
        self.messages.append(msg)
        if len(self.messages) > self.keep_recent:
            self.messages = safe_trim_messages(self.messages, self.keep_recent)
        if role == "user" and content:
            self._update_facts(content)

    def _update_facts(self, user_message):
        prompt = self.FACT_EXTRACT_PROMPT.format(
            facts=json.dumps(self.facts, ensure_ascii=False),
            user_message=user_message,
        )
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            self.stats["management_calls"] += 1
            self.stats["management_prompt_tokens"] += response.usage.prompt_tokens
            self.stats["management_completion_tokens"] += response.usage.completion_tokens

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            new_facts = json.loads(raw)
            if isinstance(new_facts, dict):
                self.facts = new_facts
        except Exception as e:
            print(f"    ⚠️  Извлечение фактов: {type(e).__name__}: {str(e)[:100]}")

    def get_api_messages(self, system_prompt):
        messages = [{"role": "system", "content": system_prompt}]
        if self.facts:
            messages.append({
                "role": "system",
                "content": "Известные факты о пользователе и задаче:\n"
                           + json.dumps(self.facts, ensure_ascii=False, indent=2),
            })
        messages.extend(self.messages)
        return messages

    def state(self):
        return {"messages": self.messages, "facts": self.facts,
                "keep_recent": self.keep_recent}

    def load_state(self, state):
        self.messages = state.get("messages", [])
        self.facts = state.get("facts", {})
        self.keep_recent = state.get("keep_recent", self.keep_recent)


# ─── Стратегия 3: Summary ────────────────────────────────────────────────────
class SummaryStrategy(ContextStrategy):
    name = "Summary"

    COMPRESS_PROMPT = """Ты — система сжатия истории диалога.
Задача: сохранить ВСЕ фактические детали, чтобы ассистент мог позже на них ссылаться.

ПРАВИЛА:
- Сохраняй имена, числа, даты, суммы, бюджеты, сроки.
- Сохраняй принятые решения, ограничения, договорённости.
- Не сохраняй приветствия, шутки, small talk.
- Пиши краткими фактами: «Имя: Игорь», «Бюджет: 250 000 ₽».
- Максимум 200 токенов.

Предыдущее резюме:
{previous_summary}

Новые сообщения:
{new_messages}

Верни только обновлённое резюме, без пояснений."""

    def __init__(self, keep_recent=10, compress_step=10):
        super().__init__()
        self.keep_recent = keep_recent
        self.compress_step = compress_step
        self.messages = []
        self.summary = ""

    def add_message(self, role, content, **extra):
        msg = {"role": role}
        if content is not None:
            msg["content"] = content
        msg.update(extra)
        self.messages.append(msg)

    def finalize_turn(self):
        if len(self.messages) < self.keep_recent + self.compress_step:
            return
        recent = safe_trim_messages(self.messages, self.keep_recent)
        to_compress = self.messages[: len(self.messages) - len(recent)]
        if not to_compress:
            return
        result = self._compress(to_compress)
        self.summary = result["summary"]
        self.messages = recent

    def _compress(self, messages_to_compress):
        prompt = self.COMPRESS_PROMPT.format(
            previous_summary=self.summary or "(пусто)",
            new_messages=self._format(messages_to_compress),
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        self.stats["management_calls"] += 1
        self.stats["management_prompt_tokens"] += response.usage.prompt_tokens
        self.stats["management_completion_tokens"] += response.usage.completion_tokens
        return {"summary": response.choices[0].message.content.strip()}

    def _format(self, messages):
        lines = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content") or ""
            if m.get("tool_calls"):
                tools = ", ".join(tc["function"]["name"] for tc in m["tool_calls"])
                content = f"[вызов: {tools}]"
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def get_api_messages(self, system_prompt):
        messages = [{"role": "system", "content": system_prompt}]
        if self.summary:
            messages.append({
                "role": "system",
                "content": "Резюме предыдущей части диалога:\n" + self.summary,
            })
        messages.extend(self.messages)
        return messages

    def state(self):
        return {"messages": self.messages, "summary": self.summary,
                "keep_recent": self.keep_recent, "compress_step": self.compress_step}

    def load_state(self, state):
        self.messages = state.get("messages", [])
        self.summary = state.get("summary", "")
        self.keep_recent = state.get("keep_recent", self.keep_recent)
        self.compress_step = state.get("compress_step", self.compress_step)