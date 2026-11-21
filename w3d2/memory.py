# memory.py
import copy
import json
from pathlib import Path

from token_counter import count_tokens


def _safe_trim(messages, keep):
    """Trim до keep, но не разрывая tool-пары."""
    if len(messages) <= keep:
        return list(messages)
    trimmed = list(messages[-keep:])
    while trimmed:
        first = trimmed[0]
        role = first.get("role")
        if role == "tool":
            trimmed = trimmed[1:]
            continue
        if role == "assistant" and first.get("tool_calls"):
            ids = {tc["id"] for tc in first["tool_calls"]}
            got = set()
            for m in trimmed[1:]:
                if m.get("role") == "tool":
                    got.add(m.get("tool_call_id"))
                else:
                    break
            if ids <= got:
                return trimmed
            i = 1
            while i < len(trimmed) and trimmed[i].get("role") == "tool":
                i += 1
            trimmed = trimmed[i:]
            continue
        return trimmed
    return trimmed


class MemoryModel:
    """Модель памяти с 4 слоями: short / working / long / profile."""

    def __init__(self, short_window=10):
        self.short = []
        self.working = {}
        self.long = {}
        self.profile = {}
        self.short_window = short_window

    # ─── Запись ────────────────────────────────────────────────────────
    def add_message(self, role, content, **extra):
        msg = {"role": role}
        if content is not None:
            msg["content"] = content
        msg.update(extra)
        self.short.append(msg)

    def add_tool_exchange(self, assistant_content, tool_calls, tool_results):
        """Атомарно: assistant с tool_calls + все tool-результаты."""
        tc_list = [{
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        } for tc in tool_calls]
        msg = {"role": "assistant", "tool_calls": tc_list}
        if assistant_content:
            msg["content"] = assistant_content
        self.short.append(msg)
        for tc, result in zip(tool_calls, tool_results):
            self.short.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })

    def trim(self):
        if len(self.short) > self.short_window:
            self.short = _safe_trim(self.short, self.short_window)

    def replace_layers(self, working, long_, profile=None):
        if isinstance(working, dict):
            self.working = working
        if isinstance(long_, dict):
            self.long = long_
        if isinstance(profile, dict):
            self.profile = profile

    # ─── Очистка ───────────────────────────────────────────────────────
    def clear_short(self):     self.short = []
    def clear_working(self):   self.working = {}
    def clear_long(self):      self.long = {}
    def clear_profile(self):   self.profile = {}
    def clear_all(self):
        self.short, self.working, self.long, self.profile = [], {}, {}, {}

    # ─── Промпт ────────────────────────────────────────────────────────
    def build_api_messages(self, system_prompt):
        messages = [{"role": "system", "content": system_prompt}]
        if self.profile:
            messages.append({
                "role": "system",
                "content": "[PROFILE: предпочтения пользователя]\n"
                           + json.dumps(self.profile, ensure_ascii=False, indent=2)
                           + "\nОБЯЗАТЕЛЬНО соблюдай эти предпочтения во всех ответах.",
            })
        if self.long:
            messages.append({
                "role": "system",
                "content": "[LONG-TERM: профиль, решения, знания]\n"
                           + json.dumps(self.long, ensure_ascii=False, indent=2),
            })
        if self.working:
            messages.append({
                "role": "system",
                "content": "[WORKING: текущая задача]\n"
                           + json.dumps(self.working, ensure_ascii=False, indent=2),
            })
        messages.extend(self.short)
        return messages

    # ─── Токены по слоям ───────────────────────────────────────────────
    def token_breakdown(self, system_prompt):
        base = count_tokens(system_prompt) + 4
        profile_tok = (count_tokens(json.dumps(self.profile, ensure_ascii=False)) + 4
                       if self.profile else 0)
        long_tok = (count_tokens(json.dumps(self.long, ensure_ascii=False)) + 4
                    if self.long else 0)
        working_tok = (count_tokens(json.dumps(self.working, ensure_ascii=False)) + 4
                       if self.working else 0)
        short_tok = sum(count_tokens(m.get("content") or "") + 4 for m in self.short)
        return {
            "system": base, "profile": profile_tok, "long": long_tok,
            "working": working_tok, "short": short_tok,
            "total": base + profile_tok + long_tok + working_tok + short_tok,
        }

    # ─── Сохранение / загрузка ─────────────────────────────────────────
    def to_dict(self):
        return {"short": self.short, "working": self.working,
                "long": self.long, "profile": self.profile,
                "short_window": self.short_window}

    @classmethod
    def from_dict(cls, data):
        m = cls(short_window=data.get("short_window", 10))
        m.short = copy.deepcopy(data.get("short", []))
        m.working = copy.deepcopy(data.get("working", {}))
        m.long = copy.deepcopy(data.get("long", {}))
        m.profile = copy.deepcopy(data.get("profile", {}))
        return m

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))