# test_day20.py
import json
import sys
from pathlib import Path

from agent import OrchestratorAgent
from multi_mcp_client import MultiMCPClient

BASE_DIR = Path(__file__).parent.resolve()
FILES_DIR = BASE_DIR / "test_files"
FILES_DIR.mkdir(exist_ok=True)


def prepare_files():
    (FILES_DIR / "spec.txt").write_text(
        "Настроить мониторинг Prometheus и алертинг",
        encoding="utf-8",
    )


def build_client(tracker_cmd=None):
    """3 сервера: fs (чужой, npx), tracker (свой), metrics (свой)."""
    m = MultiMCPClient()
    m.register(
        "fs",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem",
              str(FILES_DIR)],
        prefix="fs_",
    )
    if tracker_cmd is None:
        m.register(
            "tracker",
            command=sys.executable,
            args=["-u", "mock_tracker_server.py"],
            prefix="tracker_",
            cwd=BASE_DIR,
        )
    else:
        m.register(
            "tracker",
            command=tracker_cmd[0],
            args=tracker_cmd[1],
            prefix="tracker_",
            cwd=BASE_DIR,
        )
    m.register(
        "metrics",
        command=sys.executable,
        args=["-u", "metrics_server.py"],
        prefix="metrics_",
        cwd=BASE_DIR,
    )
    return m


def show_tools(m):
    print("\n📋 Инструменты по серверам:")
    by_server = {}
    for name, client in m.clients.items():
        prefix = m.prefixes[name]
        for t in client.list_tools():
            by_server.setdefault(name, []).append(f"{prefix}{t['name']}")
    for name, tools in by_server.items():
        print(f"   {name:<10} → {', '.join(tools)}")
    for name, st in m.status.items():
        if st != "ok":
            print(f"   {name:<10} → ❌ {st}")


def s1_full_flow(m):
    print("\n" + "=" * 64)
    print("  СЦЕНАРИЙ 1: длинный флоу по 3 серверам")
    print("=" * 64)
    agent = OrchestratorAgent(m, fs_dir=str(FILES_DIR))
    q = (
        f"Прочитай файл {FILES_DIR}\\spec.txt через fs. "
        f"Создай задачу в tracker с title, равным содержимому файла, "
        f"assignee 'DevOps', priority 'high'. "
        f"Затем получи текущую метрику CPU через metrics. "
        f"В конце перечисли все три результата."
    )
    print(f"👤 {q}\n")
    a = agent.run(q) or ""
    print(f"\n🤖 {a}")
    return {"scenario": "1_full_flow", "answer": a,
            "calls": agent.tool_calls_log}


def s2_midflow_failure(m):
    print("\n" + "=" * 64)
    print("  СЦЕНАРИЙ 2: tracker падает посреди работы")
    print("=" * 64)

    print("\n💀 Симулирую падение tracker...")
    m.kill_runtime("tracker")
    print(f"   tracker.status = {m.status['tracker']}")

    # 2a. Спрашиваем то, что требует tracker — должно быть [SERVER UNAVAILABLE]
    agent1 = OrchestratorAgent(m, fs_dir=str(FILES_DIR))
    q1 = "Создай задачу в tracker с title 'Проверка после падения'."
    print(f"\n👤 {q1}\n")
    a1 = agent1.run(q1) or ""
    print(f"\n🤖 {a1}")

    # 2b. Спрашиваем про metrics — должно работать
    agent2 = OrchestratorAgent(m, fs_dir=str(FILES_DIR))
    q2 = "Какая сейчас нагрузка CPU? Используй metrics."
    print(f"\n👤 {q2}\n")
    a2 = agent2.run(q2) or ""
    print(f"\n🤖 {a2}")

    return {"scenario": "2_midflow_failure",
            "answer_tracker": a1, "answer_metrics": a2,
            "calls_tracker": agent1.tool_calls_log,
            "calls_metrics": agent2.tool_calls_log}


def s3_down_at_startup():
    print("\n" + "=" * 64)
    print("  СЦЕНАРИЙ 3: tracker недоступен с самого старта")
    print("=" * 64)
    # Битый tracker: команда сразу завершается
    m = build_client(tracker_cmd=(sys.executable, ["-c", "import sys; sys.exit(1)"]))
    print(f"\n📊 Статусы серверов:")
    for name, st in m.status.items():
        print(f"   {name:<10} → {st}")

    agent = OrchestratorAgent(m, fs_dir=str(FILES_DIR))
    q = ("Создай задачу в tracker с title 'Тест'. "
         "Если tracker недоступен — честно скажи об этом.")
    print(f"\n👤 {q}\n")
    a = agent.run(q) or ""
    print(f"\n🤖 {a}")

    try:
        m.stop_all()
    except Exception:
        pass
    return {"scenario": "3_down_at_startup", "answer": a,
            "status": dict(m.status), "calls": agent.tool_calls_log}


def main():
    print("=" * 64)
    print("  ДЕНЬ 20: ORCHESTRATION MCP (3 сервера)")
    print("=" * 64)
    prepare_files()

    print("\n🔌 Подключаюсь ко всем серверам (fs ~15 сек на первый запуск)...")
    m = build_client()
    show_tools(m)

    results = []
    try:
        results.append(s1_full_flow(m))
        results.append(s2_midflow_failure(m))
    finally:
        m.stop_all()

    results.append(s3_down_at_startup())

    # Итоги
    print("\n" + "=" * 64)
    print("  ИТОГИ")
    print("=" * 64)
    for r in results:
        print(f"\n{r['scenario']}:")
        if "calls" in r:
            print(f"   вызовов: {len(r['calls'])}")
        if "status" in r:
            print(f"   статусы: {r['status']}")

    # Отчёт
    out_dir = BASE_DIR / "out"
    out_dir.mkdir(exist_ok=True)
    lines = ["# День 20. Orchestration MCP\n\n"]
    for r in results:
        lines.append(f"## {r['scenario']}\n\n")
        if "answer" in r:
            lines.append(f"**Ответ:**\n\n```\n{r['answer']}\n```\n\n")
        if "answer_tracker" in r:
            lines.append(f"**После падения — tracker:**\n\n"
                         f"```\n{r['answer_tracker']}\n```\n\n")
            lines.append(f"**После падения — metrics:**\n\n"
                         f"```\n{r['answer_metrics']}\n```\n\n")
        if "status" in r:
            lines.append(f"**Статусы:** `{r['status']}`\n\n")
    (out_dir / "day20_report.md").write_text(
        "".join(lines), encoding="utf-8"
    )
    print(f"\n📄 Отчёт: {out_dir / 'day20_report.md'}")


if __name__ == "__main__":
    sys.exit(main() or 0)