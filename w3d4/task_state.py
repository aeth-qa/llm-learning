# task_state.py
import json
from datetime import datetime
from pathlib import Path

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)
STATE_FILE = OUT_DIR / "task_state.json"

STATES = ["planning", "execution", "validation", "done"]

TRANSITIONS = {
    "planning":   ["execution"],
    "execution":  ["validation"],
    "validation": ["done"],
    "done":       [],
}

EXPECTED_ACTION = {
    "planning":   "Составь план и получи одобрение пользователя",
    "execution":  "Выполняй шаги утверждённого плана",
    "validation": "Проверь результат, найди проблемы",
    "done":       "Задача завершена",
}


def _default():
    return {"state": "planning", "paused": False, "history": []}


def _load():
    if not STATE_FILE.exists():
        return _default()
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default()


def _save(data):
    tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


_state = _load()


def get_current():
    return dict(_state)


def reset():
    global _state
    _state = _default()
    _save(_state)


def transition(new_state, reason=""):
    global _state
    if _state["paused"]:
        return False, (f"❌ Задача на паузе. Нельзя перейти в {new_state}. "
                       f"Сначала вызови resume_task.")
    if new_state not in STATES:
        return False, f"❌ Неизвестный этап: {new_state}. Допустимые: {STATES}"
    current = _state["state"]
    allowed = TRANSITIONS.get(current, [])
    if new_state not in allowed:
        return False, (f"❌ Нельзя перейти {current} → {new_state}. "
                       f"Из {current} допустимо: {allowed or 'ничего (этап финальный)'}.")
    _state["state"] = new_state
    _state["history"].append({
        "from": current, "to": new_state, "reason": reason,
        "at": datetime.now().isoformat(timespec="seconds"),
    })
    _save(_state)
    return True, f"✅ Переход {current} → {new_state} разрешён."


def pause(reason=""):
    global _state
    if _state["paused"]:
        return "ℹ️ Задача уже на паузе."
    _state["paused"] = True
    _state["history"].append({
        "action": "pause", "state": _state["state"], "reason": reason,
        "at": datetime.now().isoformat(timespec="seconds"),
    })
    _save(_state)
    return f"⏸ Задача на паузе (этап: {_state['state']})."


def resume():
    global _state
    if not _state["paused"]:
        return "ℹ️ Задача не на паузе."
    _state["paused"] = False
    _state["history"].append({
        "action": "resume", "state": _state["state"],
        "at": datetime.now().isoformat(timespec="seconds"),
    })
    _save(_state)
    return f"▶ Задача возобновлена (этап: {_state['state']})."


def describe():
    s = _state
    return "\n".join([
        f"Этап: {s['state']}",
        f"{'⏸ На паузе' if s['paused'] else '▶ Активна'}",
        f"Ожидаемое действие: {EXPECTED_ACTION.get(s['state'], '—')}",
        f"Допустимые переходы: {TRANSITIONS.get(s['state'], [])}",
    ])