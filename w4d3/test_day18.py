# test_day18.py
import json
import sys
import threading
import time
from pathlib import Path

from mcp_client import MCPClient

BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR = BASE_DIR / "out"
OUT_DIR.mkdir(exist_ok=True)
DATA_FILE = OUT_DIR / "metrics_data.json"

# ─── Конфигурация (Demo: 2×3; Real: 3600 × ∞) ──────────────────
TICK_INTERVAL = 2       # секунд между тиками
SESSION_1_TICKS = 3     # тиков в первой сессии (сброс данных)
SESSION_2_TICKS = 3     # тиков во второй сессии (дописывание)
# ────────────────────────────────────────────────────────────────


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_session(mcp, session_name, n_ticks, stop_event):
    """Один прогон планировщика: n_ticks тиков с интервалом TICK_INTERVAL."""
    log(f"\n{'─' * 60}")
    log(f"▶ {session_name}: {n_ticks} тиков по {TICK_INTERVAL}с")
    log(f"{'─' * 60}")

    for i in range(1, n_ticks + 1):
        if stop_event.is_set():
            log(f"   ⏹ остановлен до тика {i}")
            return

        log(f"   ⏱ тик {i}/{n_ticks}")

        raw = mcp.call_tool("fetch_metric", {})
        try:
            metric = json.loads(raw)
        except Exception as e:
            log(f"      ❌ parse error: {e}")
            continue
        log(f"      fetch_metric → value={metric['value']} ts={metric['ts']}")

        save_raw = mcp.call_tool("save_reading", {"data": metric})
        try:
            saved = json.loads(save_raw)
        except Exception:
            saved = {}
        log(f"      save_reading → saved, всего в файле: {saved.get('total', '?')}")

        if i < n_ticks:
            if stop_event.wait(TICK_INTERVAL):
                log(f"   ⏹ прерван на паузе")
                return

    log(f"   ✅ {session_name} завершена.")


def main():
    log("=" * 60)
    log("ПЛАНИРОВЩИК + MCP: сбор метрик и сводка за период")
    log(f"Demo: {SESSION_1_TICKS}×{TICK_INTERVAL}с + "
        f"{SESSION_2_TICKS}×{TICK_INTERVAL}с")
    log("=" * 60)

    # Чистый старт — удаляем данные прошлых запусков
    if DATA_FILE.exists():
        DATA_FILE.unlink()
        log(f"🗑  Удалён старый {DATA_FILE.name}")

    log("\n🔌 Подключаюсь к MCP...")
    mcp = MCPClient(
        command=sys.executable,
        args=["-u", "metrics_server.py"],
        cwd=BASE_DIR,
    )
    mcp.start()
    tools = mcp.list_tools()
    log(f"✅ Подключено, инструментов: {len(tools)}")
    for t in tools:
        log(f"   • {t['name']}")

    stop_event = threading.Event()
    try:
        # ─── Сессия 1: чистая запись ───────────────────────────
        run_session(mcp, "СЕССИЯ 1 (reset)", SESSION_1_TICKS, stop_event)

        # ─── Сессия 2: дописываем к сессии 1 ────────────────────
        run_session(mcp, "СЕССИЯ 2 (append)", SESSION_2_TICKS, stop_event)

        # ─── Финальный агрегированный отчёт ─────────────────────
        log("\n" + "=" * 60)
        log("📊 АГРЕГИРОВАННЫЙ ОТЧЁТ (по ВСЕМ накопленным данным)")
        log("=" * 60)

        all_raw = mcp.call_tool("read_readings", {})
        try:
            payload = json.loads(all_raw)
        except Exception as e:
            log(f"⚠️ не удалось распарсить read_readings: {e}")
            payload = {}
        all_data = payload.get("readings", [])
        log(f"Прочитано записей: {len(all_data)} (count по серверу: "
            f"{payload.get('count', '?')})")
        for i, r in enumerate(all_data, 1):
            log(f"  {i}. ts={r.get('ts')}  value={r.get('value')}")

        summary_raw = mcp.call_tool("summarize", {})
        try:
            summary = json.loads(summary_raw)
        except Exception:
            summary = {}
        log("\nСводка (computed by MCP server):")
        for k, v in summary.items():
            log(f"  {k}: {v}")

        # ─── LLM-нарратив по сводке (единственный вызов LLM) ─────
        log("\n" + "=" * 60)
        log("🤖 LLM-нарратив (один вызов — только на финальный отчёт)")
        log("=" * 60)
        try:
            from config import client, MODEL
            prompt = (
                "Ты — аналитик мониторинга. Вот сводка метрик CPU за период:\n"
                f"{json.dumps(summary, ensure_ascii=False, indent=2)}\n\n"
                "Напиши короткий отчёт (3–5 предложений): стабильна ли система, "
                "были ли аномалии, что рекомендуешь."
            )
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            print("\n" + resp.choices[0].message.content.strip())
        except Exception as e:
            log(f"⚠️ LLM недоступен: {e}")

        log(f"\n✅ Готово. Файл данных: {DATA_FILE}")

    except KeyboardInterrupt:
        log("\n⚠️ Ctrl+C, останавливаю планировщик...")
        stop_event.set()
    finally:
        log("\n🔌 Отключаюсь от MCP...")
        mcp.stop()
        log("✅ Отключено.")


if __name__ == "__main__":
    sys.exit(main() or 0)