# test_day17.py
import json
import sys
from pathlib import Path

from agent import SimpleAgent
from mcp_client import MCPClient

BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR = BASE_DIR / "out"
OUT_DIR.mkdir(exist_ok=True)


def main():
    print("=" * 64)
    print("  ПОДКЛЮЧЕНИЕ К СВОЕМУ MCP-СЕРВЕРУ")
    print("=" * 64)

    # sys.executable — это full path к текущему Python. Надёжнее, чем "py".
    mcp = MCPClient(
        command=sys.executable,
        args=["mock_tracker_server.py"],
        cwd=BASE_DIR,
    )
    mcp.start(timeout=60)

    tools = mcp.list_tools()
    print(f"\n✅ Подключено. Получено {len(tools)} инструментов:")
    for t in tools:
        print(f"   • {t['name']} — {t['description'].splitlines()[0]}")

    try:
        agent = SimpleAgent(mcp_client=mcp)
        print(f"\nВсего в tools_schema: {len(agent.tools_schema)} "
              f"(1 локальный + {len(tools)} MCP)")

        # Сохраняем тело запроса
        sample = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "<пример>"}],
            "tools": agent.tools_schema,
        }
        (OUT_DIR / "request_body.json").write_text(
            json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ─── Сценарий 1: чтение (список) ───────────────────────────────
        print("\n" + "=" * 64)
        print("  СЦЕНАРИЙ 1: список открытых задач")
        print("=" * 64)
        q1 = "Покажи все задачи со статусом open. Кратко перечисли ID и названия."
        print(f"👤 {q1}\n")
        print(f"🤖 {agent.run(q1)}")

        # ─── Сценарий 2: чтение конкретной задачи ──────────────────────
        print("\n" + "=" * 64)
        print("  СЦЕНАРИЙ 2: детали задачи TASK-1")
        print("=" * 64)
        q2 = "Что за задача TASK-1? Кто её исполнитель и какой у неё приоритет?"
        print(f"👤 {q2}\n")
        print(f"🤖 {agent.run(q2)}")

        # ─── Сценарий 3: запись (создание) ─────────────────────────────
        print("\n" + "=" * 64)
        print("  СЦЕНАРИЙ 3: создать задачу + проверить, что она в списке")
        print("=" * 64)
        q3 = ("Создай задачу «Настроить мониторинг Prometheus» на исполнителя "
              "DevOps с приоритетом high. После создания покажи все открытые "
              "задачи, чтобы убедиться, что новая задача там есть.")
        print(f"👤 {q3}\n")
        print(f"🤖 {agent.run(q3)}")

        # ─── Сценарий 4: модификация (смена статуса) ───────────────────
        print("\n" + "=" * 64)
        print("  СЦЕНАРИЙ 4: перевести TASK-2 в closed + показать закрытые")
        print("=" * 64)
        q4 = ("Переведи задачу TASK-2 в статус closed, потом покажи список "
              "всех закрытых задач.")
        print(f"👤 {q4}\n")
        print(f"🤖 {agent.run(q4)}")

        # ─── Финальная проверка состояния сервера ─────────────────────
        print("\n" + "=" * 64)
        print("  ФИНАЛЬНАЯ ПРОВЕРКА (прямой вызов через MCP, без модели)")
        print("=" * 64)
        all_tasks = mcp.call_tool("list_tasks", {"status": "all"})
        print("Все задачи на сервере:")
        print(all_tasks[:600])

        s = agent.session_stats
        print(f"\nAPI-вызовов: {s['calls']}, "
              f"prompt={s['prompt_tokens']}, completion={s['completion_tokens']}")
    finally:
        print("\n🔌 Отключаюсь от MCP...")
        mcp.stop()
        print("✅ Отключено.")


if __name__ == "__main__":
    sys.exit(main())
    sys.exit(main())