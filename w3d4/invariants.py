import json
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
FILE = OUT / "invariants.json"

DEFAULTS = {
    "INV-001": "БД только PostgreSQL 16 + pg_cron. MongoDB и другие NoSQL запрещены.",
    "INV-002": "Бюджет финальный 247 300 ₽. Увеличение запрещено.",
    "INV-003": "MVP включает только заказ и оплату. Доставка, лояльность, отзывы — вне scope.",
    "INV-004": "Платёжная интеграция только YooKassa. Stripe, PayPal и другие — запрещены.",
}


def _load():
    if not FILE.exists():
        return {"invariants": dict(DEFAULTS), "history": []}
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"invariants": dict(DEFAULTS), "history": []}


def _save(d):
    tmp = FILE.with_name(FILE.name + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(FILE)


_state = _load()


def get_all():
    return dict(_state["invariants"])


def get_history():
    return list(_state["history"])


def change(inv_id, new_text, reason, actor="cli"):
    if inv_id not in _state["invariants"]:
        return False, f"❌ Нет инварианта {inv_id}"
    if not new_text.strip():
        return False, "❌ Пустой текст инварианта"
    old = _state["invariants"][inv_id]
    _state["invariants"][inv_id] = new_text.strip()
    _state["history"].append({
        "at": datetime.now().isoformat(timespec="seconds"),
        "id": inv_id, "from": old, "to": new_text.strip(),
        "reason": reason, "actor": actor,
    })
    _save(_state)
    return True, f"✅ {inv_id}: «{old[:40]}…» → «{new_text.strip()[:40]}…»"