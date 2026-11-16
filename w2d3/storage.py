# storage.py
import json
from pathlib import Path

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)
HISTORY_FILE = OUT_DIR / "history.json"


def load_history():
    """Загружает историю. Возвращает список сообщений (без system)."""
    if not HISTORY_FILE.exists():
        return []

    try:
        text = HISTORY_FILE.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("Ожидался список сообщений")
        if not all(isinstance(m, dict) and "role" in m for m in data):
            raise ValueError("Некорректная структура сообщений")
        return data
    except (json.JSONDecodeError, ValueError) as e:
        # Файл повреждён — переименовываем и начинаем с чистого листа
        broken = HISTORY_FILE.with_name(HISTORY_FILE.name + ".broken")
        HISTORY_FILE.replace(broken)
        print(f"⚠️  Файл истории повреждён ({e}).")
        print(f"    Переименован в: {broken.name}")
        print(f"    Начинаем с пустой истории.\n")
        return []


def save_history(messages):
    """Атомарно сохраняет историю (без system-сообщения)."""
    # System пропускаем — при загрузке всегда добавляем свежий
    to_save = [m for m in messages if m.get("role") != "system"]

    # Атомарная запись: tmp → rename
    tmp = HISTORY_FILE.with_name(HISTORY_FILE.name + ".tmp")
    tmp.write_text(
        json.dumps(to_save, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(HISTORY_FILE)  # атомарная операция ОС