# memory.py
import copy
import json
from datetime import datetime
from pathlib import Path

from token_counter import count_tokens


# Ключи, значения которых накапливаются списком, а не перезаписываются
LIST_FACT_KEYS = {
    "решения", "decisions", "принятые решения",
    "история изменений", "requirements_history",
}


def _safe_trim(messages, keep):
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
    """Память с 4 слоями. long хранит {key: {value, ts, type}} + журнал изменений."""

    def __init__(self, short_window=10):
        self.short = []
        self.working = {}
        self.long = {}               # новая структура
        self.profile = {}
        self.changes_log = []        # [{at, key, action, from?, to}]
        self.short_window = short_window

    # ─── short ─────────────────────────────────────────────────────────
    def add_message(self, role, content, **extra):
        msg = {"role": role}
        if content is not None:
            msg["content"] = content
        msg.update(extra)
        self.short.append(msg)

    def add_tool_exchange(self, assistant_content, tool_calls, tool_results):
        tc_list = [{
            "id": tc.id, "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        } for tc in tool_calls]
        msg = {"role": "assistant", "tool_calls": tc_list}
        if assistant_content:
            msg["content"] = assistant_content
        self.short.append(msg)
        for tc, result in zip(tool_calls, tool_results):
            self.short.append({
                "role": "tool", "tool_call_id": tc.id, "content": str(result),
            })

    def trim(self):
        if len(self.short) > self.short_window:
            self.short = _safe_trim(self.short, self.short_window)

    # ─── working / profile: полная замена ──────────────────────────────
    def replace_working(self, working):
        if isinstance(working, dict):
            self.working = working

    def replace_profile(self, profile):
        if isinstance(profile, dict):
            self.profile = profile

    # ─── long: применение дельт ────────────────────────────────────────
    def apply_facts(self, updates):
        """updates: {key: new_value}. Код решает, replace или append."""
        if not isinstance(updates, dict):
            return
        ts = datetime.now().isoformat(timespec="seconds")
        for key, new_val in updates.items():
            if not key or new_val is None:
                continue
            new_val = str(new_val).strip()
            if not new_val:
                continue

            is_list = key in LIST_FACT_KEYS

            if is_list:
                if key not in self.long:
                    self.long[key] = {"value": [new_val], "ts": ts, "type": "list"}
                    self.changes_log.append({
                        "at": ts, "key": key, "action": "add_list",
                        "to": new_val,
                    })
                else:
                    existing = self.long[key]["value"]
                    if not isinstance(existing, list):
                        existing = [existing]
                    if new_val not in existing:
                        existing.append(new_val)
                        self.long[key]["value"] = existing
                        self.long[key]["ts"] = ts
                        self.changes_log.append({
                            "at": ts, "key": key, "action": "append",
                            "to": new_val,
                        })
            else:
                if key in self.long:
                    old = self.long[key]["value"]
                    if old != new_val:
                        self.long[key] = {"value": new_val, "ts": ts, "type": "scalar"}
                        self.changes_log.append({
                            "at": ts, "key": key, "action": "replace",
                            "from": old, "to": new_val,
                        })
                else:
                    self.long[key] = {"value": new_val, "ts": ts, "type": "scalar"}
                    self.changes_log.append({
                        "at": ts, "key": key, "action": "add",
                        "to": new_val,
                    })

    def _flatten_long(self):
        """Плоский вид для промпта: без ts и type."""
        return {k: v["value"] for k, v in self.long.items()}

    # ─── завершение задачи ─────────────────────────────────────────────
    def finish_task(self):
        """Явный метод: очищает рабочую память, long и profile сохраняются."""
        self.working = {}
        self.short = []
        return "🧹 Рабочая память очищена. Long и profile сохранены."

    # ─── очистка ───────────────────────────────────────────────────────
    def clear_short(self):     self.short = []
    def clear_working(self):   self.working = {}
    def clear_long(self):      self.long = {}; self.changes_log = []
    def clear_profile(self):   self.profile = {}
    def clear_all(self):
        self.short, self.working, self.long = [], {}, {}
        self.profile, self.changes_log = {}, []

    # ─── промпт ────────────────────────────────────────────────────────
    def build_api_messages(self, system_prompt):
        messages = [{"role": "system", "content": system_prompt}]
        if self.profile:
            messages.append({
                "role": "system",
                "content": "[PROFILE: предпочтения пользователя]\n"
                           + json.dumps(self.profile, ensure_ascii=False, indent=2)
                           + "\nОБЯЗАТЕЛЬНО соблюдай эти предпочтения во всех ответах.",
            })
        flat = self._flatten_long()
        if flat:
            messages.append({
                "role": "system",
                "content": "[LONG-TERM: актуальные факты]\n"
                           + json.dumps(flat, ensure_ascii=False, indent=2),
            })
        if self.working:
            messages.append({
                "role": "system",
                "content": "[WORKING: текущая задача]\n"
                           + json.dumps(self.working, ensure_ascii=False, indent=2),
            })
        messages.extend(self.short)
        return messages

    def token_breakdown(self, system_prompt):
        base = count_tokens(system_prompt) + 4
        profile_tok = (count_tokens(json.dumps(self.profile, ensure_ascii=False)) + 4
                       if self.profile else 0)
        long_tok = (count_tokens(json.dumps(self._flatten_long(), ensure_ascii=False)) + 4
                    if self.long else 0)
        working_tok = (count_tokens(json.dumps(self.working, ensure_ascii=False)) + 4
                       if self.working else 0)
        short_tok = sum(count_tokens(m.get("content") or "") + 4 for m in self.short)
        return {
            "system": base, "profile": profile_tok, "long": long_tok,
            "working": working_tok, "short": short_tok,
            "total": base + profile_tok + long_tok + working_tok + short_tok,
        }

    # ─── сериализация ──────────────────────────────────────────────────
    def to_dict(self):
        return {
            "short": self.short, "working": self.working,
            "long": self.long, "profile": self.profile,
            "changes_log": self.changes_log,
            "short_window": self.short_window,
        }

    @classmethod
    def from_dict(cls, data):
        m = cls(short_window=data.get("short_window", 10))
        m.short = copy.deepcopy(data.get("short", []))
        m.working = copy.deepcopy(data.get("working", {}))
        m.profile = copy.deepcopy(data.get("profile", {}))
        m.changes_log = copy.deepcopy(data.get("changes_log", []))

        raw_long = data.get("long", {})
        for k, v in raw_long.items():
            if isinstance(v, dict) and "value" in v:
                m.long[k] = copy.deepcopy(v)
            else:
                # Legacy-формат: {key: value} → обернуть
                m.long[k] = {"value": v, "ts": "legacy", "type": "scalar"}
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