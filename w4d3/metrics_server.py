# metrics_server.py
"""MCP-сервер: сбор метрик CPU (random walk) с накоплением в JSON.

Инструменты:
  - fetch_metric()        → новое показание
  - save_reading(data)    → дописать в out/metrics_data.json
  - read_readings()       → все накопленные записи
  - summarize()           → count/avg/min/max по всем записям
"""
import json
import random
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("metrics-collector")

DATA_FILE = Path(__file__).parent / "out" / "metrics_data.json"

# Состояние random walk (между вызовами живёт в памяти сервера)
_last_value = [50.0]


@mcp.tool()
def fetch_metric() -> dict:
    """Получить текущее значение метрики (CPU load %, random walk)."""
    delta = random.uniform(-10, 10)
    new_value = max(5.0, min(95.0, _last_value[0] + delta))
    _last_value[0] = new_value
    return {
        "metric": "cpu_load",
        "value": round(new_value, 2),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }


@mcp.tool()
def save_reading(data: dict) -> dict:
    """Сохранить показание в JSON-файл (накопление между запусками)."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if DATA_FILE.exists():
        try:
            history = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append(data)
    DATA_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"saved": True, "total": len(history)}


@mcp.tool()
def read_readings() -> dict:
    """Вернуть все накопленные показания."""
    if not DATA_FILE.exists():
        return {"readings": [], "count": 0}
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return {"readings": data, "count": len(data)}
    except Exception as e:
        return {"readings": [], "count": 0, "error": str(e)}


@mcp.tool()
def summarize() -> dict:
    """Агрегированная сводка по ВСЕМ накопленным записям."""
    result = read_readings()
    readings = result.get("readings", [])
    if not readings:
        return {"count": 0, "message": "Нет данных"}
    values = [r["value"] for r in readings if "value" in r]
    if not values:
        return {"count": 0, "message": "Нет валидных значений"}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "first_ts": readings[0].get("ts"),
        "last_ts": readings[-1].get("ts"),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")