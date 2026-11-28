# agent.py
import json
from config import client, MODEL

SYSTEM_PROMPT_TEMPLATE = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом, "
    "без markdown-разметки.\n\n"
    "Ты работаешь с MCP-инструментами от нескольких серверов. "
    "Имена инструментов имеют префикс сервера: `fs_`, `tracker_`, `metrics_`. "
    "В описании каждого инструмента указан сервер в квадратных скобках.\n\n"
    "ДОСТУПНЫЕ СЕРВЕРЫ:\n{servers_block}\n\n"
    "Filesystem: разрешённая директория — {fs_dir}. "
    "Используй полный путь к файлам, например {fs_dir}\\spec.txt.\n\n"
    "ПРАВИЛА:\n"
    "1. Если нужный сервер недоступен — честно скажи, что он упал, "
    "   назови причину. НЕ ВЫДУМЫВАЙ результат.\n"
    "2. Если инструмент вернул [SERVER UNAVAILABLE] — остановись и объясни.\n"
    "3. Используй инструменты по одному, дожидаясь результата."
)


class OrchestratorAgent:
    def __init__(self, multi_client, fs_dir="", max_iterations=10):
        self.multi = multi_client
        self.fs_dir = fs_dir
        self.max_iterations = max_iterations
        self.tools_schema = multi_client.get_aggregated_tools(
            allow_per_server={
                "fs": {"read_text_file", "read_file",
                       "write_file", "list_directory"},
                "metrics": {"fetch_metric"},
            }
        )
        self.tool_calls_log = []

    def run(self, user_query):
        self.tool_calls_log = []
        system = SYSTEM_PROMPT_TEMPLATE.format(
            servers_block=self.multi.describe_servers(),
            fs_dir=self.fs_dir,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_query},
        ]

        for _ in range(self.max_iterations):
            resp = client.chat.completions.create(
                model=MODEL, messages=messages,
                tools=self.tools_schema, tool_choice="auto",
            )
            msg = resp.choices[0].message
            finish = resp.choices[0].finish_reason

            if finish == "tool_calls":
                messages.append(msg.model_dump())
                for tc in msg.tool_calls:
                    name = tc.function.name
                    args = json.loads(tc.function.arguments)
                    server, _ = self.multi.tool_to_server(name)
                    print(f"    🔧 [{server or '?'}] {name}({args})")
                    result = self.multi.call_routed(name, args)
                    print(f"       → {result[:160]}")
                    self.tool_calls_log.append({
                        "tool": name, "server": server,
                        "args": args, "result": result,
                    })
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id,
                        "content": result,
                    })
                continue

            return msg.content

        return "Достигнут лимит итераций."