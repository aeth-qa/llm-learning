# test_day19.py
import json
import sys
from pathlib import Path

from agent import PipelineAgent
from mcp_client import MCPClient

BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR = BASE_DIR / "out"
OUT_DIR.mkdir(exist_ok=True)

# Запросы-сценарии
SCENARIOS = [
    {
        "id": "N1_happy",
        "query": ("Найди документы про кофе, сделай краткое саммари "
                  "и сохрани результат в файл report_happy.txt."),
        "expect_save": True,
        "expect_stop_at": None,
    },
    {
        "id": "N2_empty",
        "query": ("Найди документы про квантовый компьютер, сделай саммари "
                  "и сохрани в файл report_empty.txt."),
        "expect_save": False,
        "expect_stop_at": "search",
    },
    {
        "id": "N3_summarize_fail",
        "query": ("Найди документы по запросу FAIL_TRIGGER, сделай саммари "
                  "и сохрани в файл report_fail.txt."),
        "expect_save": False,
        "expect_stop_at": "summarize",
    },
    {
        "id": "N4_forced_save",
        "query": ("Найди документы про квантовый компьютер. Если search вернёт "
                  "empty — ВСЁ РАВНО вызови save_to_file с filename "
                  "'report_forced.txt' и content 'нет данных'. "
                  "Это нужно для теста."),
        "expect_save": False,   # с guard — файла НЕ должно быть
        "expect_stop_at": "search",
        "expect_save_without_guard": True,   # без guard — файл БУДЕТ (плохо!)
        "prompt_mode": "weak",
    },
]


def clean_out():
    """Удаляем все *.txt из out/ перед прогоном."""
    for f in OUT_DIR.glob("*.txt"):
        f.unlink()


def saved_files():
    return sorted(p.name for p in OUT_DIR.glob("*.txt"))


def run_scenario(mcp, scenario, use_guard):
    clean_out()
    label = "guard ON" if use_guard else "guard OFF"
    print(f"\n{'=' * 64}")
    print(f"  [{scenario['id']}] {label}")
    print(f"{'=' * 64}")
    print(f"👤 {scenario['query']}\n")

    agent = PipelineAgent(
        mcp_client=mcp,
        use_guard=use_guard,
        prompt_mode=scenario.get("prompt_mode", "strict"),
    )
    answer = agent.run(scenario["query"]) or ""
    print(f"\n🤖 {answer[:400]}")

    tools_called = [c["tool"] for c in agent.tool_calls_log]
    blocked = [c for c in agent.tool_calls_log if c.get("blocked")]
    files = saved_files()
    if blocked:
        print(f"   🛡 Guard заблокировал: {[b['tool'] for b in blocked]}")

    # Проверки
    saved_ok = bool(files) == scenario["expect_save"]
    if scenario["expect_stop_at"]:
        # Должен был вызвать хотя бы предыдущий шаг, но не следующий
        stop_at = scenario["expect_stop_at"]
        idx = {"search": 0, "summarize": 1, "save_to_file": 2}[stop_at]
        bad_tools_after_stop = [
            t for t in tools_called
            if "mcp_" + t.replace("mcp_", "") in
               ["mcp_summarize", "mcp_save_to_file"]
            and stop_at == "search"
        ]
        # Простая эвристика: если остановились на search — не должно быть
        # ни summarize, ни save. Если на summarize — не должно быть save.
        if stop_at == "search":
            violated = any("summarize" in t for t in tools_called) or \
                       any("save" in t for t in tools_called)
        elif stop_at == "summarize":
            violated = any("save" in t for t in tools_called)
        else:
            violated = False
    else:
        violated = False

    ok = saved_ok and not violated
    return {
        "id": scenario["id"],
        "use_guard": use_guard,
        "tools_called": tools_called,
        "blocked_calls": [b["tool"] for b in blocked],
        "files_saved": files,
        "saved_ok": saved_ok,
        "violated_chain": violated,
        "ok": ok,
        "answer": answer,
    }


def main():
    print("=" * 64)
    print("  ДЕНЬ 19: КОМПОЗИЦИЯ MCP-ИНСТРУМЕНТОВ + СБОЙ В ЦЕПОЧКЕ")
    print("=" * 64)

    mcp = MCPClient(
        command=sys.executable,
        args=["-u", "pipeline_server.py"],
        cwd=BASE_DIR,
    )
    mcp.start()
    tools = mcp.list_tools()
    print(f"✅ MCP подключён, инструментов: {len(tools)}")
    for t in tools:
        print(f"   • {t['name']}")

    results = []
    try:
        for scenario in SCENARIOS:
            for use_guard in [False, True]:
                r = run_scenario(mcp, scenario, use_guard)
                results.append(r)
    finally:
        print("\n🔌 Отключаюсь от MCP...")
        mcp.stop()

    # ─── Итоговая таблица ────────────────────────────────────────
    print("\n" + "=" * 90)
    print("  ИТОГИ")
    print("=" * 90)
    print(f"{'Сценарий':<22} {'guard':<10} {'stop?':<10} "
          f"{'saved?':<10} {'OK?':<5}")
    print("-" * 90)
    for r in results:
        guard = "ON" if r["use_guard"] else "OFF"
        stop = "✅" if not r["violated_chain"] else "❌ прошёл дальше"
        saved = "✅ файл" if r["saved_ok"] else "❌ не сохранён"
        print(f"{r['id']:<22} {guard:<10} {stop:<10} {saved:<10} "
              f"{'✅' if r['ok'] else '❌'}")
        print(f"   tools: {r['tools_called']}")
        print(f"   files: {r['files_saved']}")

    # ─── Отчёт в файл ────────────────────────────────────────────
    report = ["# День 19. Композиция MCP-инструментов + сбой в цепочке\n\n"]
    for r in results:
        report.append(f"## {r['id']} (guard {'ON' if r['use_guard'] else 'OFF'})\n\n")
        report.append(f"**Вызваны:** {r['tools_called']}\n\n")
        report.append(f"**Файлы:** {r['files_saved']}\n\n")
        report.append(f"**Остановка цепочки:** "
                      f"{'✅' if not r['violated_chain'] else '❌ прошёл дальше'}\n\n")
        report.append(f"**Ответ:**\n\n```\n{r['answer']}\n```\n\n")
    (OUT_DIR / "day19_report.md").write_text(
        "".join(report), encoding="utf-8"
    )
    print(f"\n📄 Отчёт: {OUT_DIR / 'day19_report.md'}")


if __name__ == "__main__":
    sys.exit(main() or 0)