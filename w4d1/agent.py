# agent.py
import json
from config import client, MODEL
from tools import TOOLS_SCHEMA, TOOLS_MAP
from mcp_tools import mcp_tools_to_openai_schema


class SimpleAgent:
    def __init__(self, mcp_client=None, max_iterations=10):
        self.mcp_client = mcp_client
        self.max_iterations = max_iterations
        self.session_stats = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

        # Объединяем локальные и MCP-инструменты в один список
        tools = list(TOOLS_SCHEMA)
        if mcp_client is not None:
            mcp_tools = mcp_client.list_tools()
            tools.extend(mcp_tools_to_openai_schema(mcp_tools))
        self.tools_schema = tools
        # Карта для локальных (MCP — через mcp_client)
        self.local_tools = dict(TOOLS_MAP)

    def _execute_tool(self, name, args):
        if name.startswith("mcp_"):
            if self.mcp_client is None:
                return "Ошибка: MCP-клиент не подключён."
            return self.mcp_client.call_tool(name[4:], args)
        fn = self.local_tools.get(name)
        if fn is None:
            return f"Ошибка: инструмент '{name}' не найден."
        try:
            return str(fn(**args))
        except Exception as e:
            return f"Ошибка '{name}': {e}"

    def run(self, user_query):
        messages = [{"role": "user", "content": user_query}]

        for iteration in range(1, self.max_iterations + 1):
            print(f"  [Итерация {iteration}]")
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=self.tools_schema,
                tool_choice="auto",
            )

            u = response.usage
            self.session_stats["calls"] += 1
            self.session_stats["prompt_tokens"] += u.prompt_tokens
            self.session_stats["completion_tokens"] += u.completion_tokens

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "tool_calls":
                messages.append(message.model_dump())
                for tc in message.tool_calls:
                    args = json.loads(tc.function.arguments)
                    result = self._execute_tool(tc.function.name, args)
                    print(f"    🔧 {tc.function.name}({args}) → {result[:100]}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                continue

            return message.content

        return "Не удалось получить ответ."