# test_day16.py
import json
import sys
from pathlib import Path

from agent import SimpleAgent
from mcp_client import MCPClient

BASE_DIR = Path(__file__).parent.resolve()
FILES_DIR = BASE_DIR / "test_files"
OUT_DIR = BASE_DIR / "out"
OUT_DIR.mkdir(exist_ok=True)


def prepare_files():
    FILES_DIR.mkdir(exist_ok=True)
    (FILES_DIR / "note.txt").write_text(
        "Привет, это тестовый файл для MCP.", encoding="utf-8"
    )
    (FILES_DIR / "budget.txt").write_text("247300", encoding="utf-8")


def main():
    prepare_files()

    print("=" * 64)
    print("  ШАГ 1: Подключение к MCP filesystem серверу")
    print("=" * 64)

    mcp = MCPClient(
        command="npx",
        args=[
            "-y", "@modelcontextprotocol/server-filesystem",
            str(FILES_DIR),
        ],
    )
    mcp.start()
    tools = mcp.list_tools()
    print(f"✅ Подключено. Получено {len(tools)} инструментов:")
    for t in tools:
        print(f"   • {t['name']}")

    try:
        agent = SimpleAgent(mcp_client=mcp)
        print(f"\nВсего в tools_schema: {len(agent.tools_schema)} инструментов "
              f"(1 локальный + {len(tools)} MCP)")

        # ─── Печать тела запроса ───────────────────────────────────────
        sample_request = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "<пример>"}],
            "tools": agent.tools_schema,
        }
        (OUT_DIR / "request_body.json").write_text(
            json.dumps(sample_request, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n📄 Тело запроса (шаблон): {OUT_DIR / 'request_body.json'}")
        print(f"   Первые 300 символов:")
        print("   " + json.dumps(sample_request, ensure_ascii=False)[:300] + "...")

        # ─── Сценарий 1: только MCP ────────────────────────────────────
        print("\n" + "=" * 64)
        print("  СЦЕНАРИЙ 1: только MCP-инструмент")
        print("=" * 64)
        q1 = "Прочитай файл note.txt из разрешённой директории и верни его содержимое."
        print(f"👤 {q1}\n")
        a1 = agent.run(q1)
        print(f"\n🤖 {a1}")

        # ─── Сценарий 2: смешанный ─────────────────────────────────────
        print("\n" + "=" * 64)
        print("  СЦЕНАРИЙ 2: MCP + локальный (смешанный)")
        print("=" * 64)
        q2 = ("Прочитай файл budget.txt из разрешённой директории и посчитай, "
              "сколько будет это число, умноженное на 1.2. "
              "Используй инструменты, не считай в уме.")
        print(f"👤 {q2}\n")
        a2 = agent.run(q2)
        print(f"\n🤖 {a2}")
        
        # ─── Сценарий 3: MCP-запись файла ──────────────────────────────
        print("\n" + "=" * 64)
        print("  СЦЕНАРИЙ 3: MCP-запись (агент создаёт файл)")
        print("=" * 64)
        out_file = FILES_DIR / "result.txt"
        if out_file.exists():
            out_file.unlink()   # чистый старт

        q3 = ("Вычисли значение выражения 247300 * 1.2 и сохрани результат "
              "в файл result.txt в разрешённой директории. "
              "Используй инструменты для вычисления и записи, "
              "не считай в уме и не пиши файлы напрямую.")
        print(f"👤 {q3}\n")
        a3 = agent.run(q3)
        print(f"\n🤖 {a3}")

        # Проверяем, что файл реально появился на диске
        print("\n  Проверка результата на диске:")
        if out_file.exists():
            content = out_file.read_text(encoding="utf-8").strip()
            print(f"    ✅ Файл создан: {out_file}")
            print(f"    Содержимое: «{content}»")
            if "296760" in content or "296 760" in content:
                print("    ✅ Содержит ожидаемое число 296760")
            else:
                print("    ⚠️ Число 296760 не найдено в содержимом")
        else:
            print(f"    ❌ Файл {out_file} не создан")

        # ─── Финальная статистика ──────────────────────────────────────
        s = agent.session_stats
        print("\n" + "=" * 64)
        print("  ИТОГИ")
        print("=" * 64)
        print(f"  Вызовов API: {s['calls']}")
        print(f"  Prompt-токенов: {s['prompt_tokens']}")
        print(f"  Completion-токенов: {s['completion_tokens']}")
    finally:
        print("\n🔌 Отключаюсь от MCP...")
        mcp.stop()
        print("✅ MCP-сессия закрыта.")


if __name__ == "__main__":
    sys.exit(main())