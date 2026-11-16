# storage.py
import json
from pathlib import Path

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)
HISTORY_FILE = OUT_DIR / "history.json"
SUMMARY_FILE = OUT_DIR / "summary.json"
ARCHIVE_FILE = OUT_DIR / "archive.json"


def _atomic_write(path, data):
    """Атомарная запись через tmp → replace."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _safe_read(path, default):
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        broken = path.with_name(path.name + ".broken")
        path.replace(broken)
        print(f"⚠️  Файл {path.name} повреждён ({e}). Переименован в {broken.name}.")
        return default


# ─── История (горячие сообщения, последние N) ───────────────────────────────
def load_history():
    data = _safe_read(HISTORY_FILE, [])
    return data if isinstance(data, list) else []


def save_history(messages):
    to_save = [m for m in messages if m.get("role") != "system"]
    _atomic_write(HISTORY_FILE, to_save)


# ─── Резюме старой части ────────────────────────────────────────────────────
def load_summary():
    data = _safe_read(SUMMARY_FILE, {"summary": ""})
    return data.get("summary", "") if isinstance(data, dict) else ""


def save_summary(text):
    _atomic_write(SUMMARY_FILE, {"summary": text})


# ─── Архив (append-only, для аудита) ────────────────────────────────────────
def load_archive():
    data = _safe_read(ARCHIVE_FILE, [])
    return data if isinstance(data, list) else []


def append_archive(messages_to_add):
    archive = load_archive()
    archive.extend(messages_to_add)
    _atomic_write(ARCHIVE_FILE, archive)


# ─── Сброс всего ────────────────────────────────────────────────────────────
def reset_all():
    save_history([])
    save_summary("")
    _atomic_write(ARCHIVE_FILE, [])