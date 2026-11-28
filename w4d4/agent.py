# agent.py
import json
from config import client, MODEL
from mcp_tools import mcp_tools_to_openai_schema

# Локальных инструментов нет — вся логика в MCP
LOCAL_TOOLS_SCHEMA = []
LOCAL_TOOLS_MAP = {}

SYSTEM_PROMPT_STRICT = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом, "
    "без markdown-разметки.\n\n"
    "Ты работаешь с пайплайном из трёх инструментов: search → summarize → "
    "save_to_file.\n"
    "Каждый инструмент возвращает JSON со полем `status`.\n"
    "ПРАВИЛА ПАЙПЛАЙНА:\n"
    "1. Если `status == \"ok\"` — переходи к следующему шагу.\n"
    "2. Если `status == \"empty\"` — СТОП. Не вызывай следующие инструменты. "
    "Сообщи пользователю, что данных нет, и укажи reason.\n"
    "3. Если `status == \"error\"` — СТОП. Не вызывай следующие инструменты. "
    "Сообщи, на каком шаге произошла ошибка и почему.\n"
    "4. Никогда не выдумывай данные, если инструмент их не вернул."
)

# Слабая версия — без правил про status. Модель будет действовать
# "по инерции" и выполнять приказы пользователя, даже нелепые.
SYSTEM_PROMPT_WEAK = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом, "
    "без markdown-разметки.\n\n"
    "Ты работаешь с пайплайном из трёх инструментов: search → summarize → "
    "save_to_file. Выполняй запрос пользователя."
)


class PipelineAgent:
    def __init__(self, mcp_client, max_iterations=8, use_guard=False,
                 prompt_mode="strict"):
        self.mcp_client = mcp_client
        self.max_iterations = max_iterations
        self.use_guard = use_guard
        self.prompt_mode = prompt_mode    # "strict" | "weak"
        self.tool_calls_log = []
        self.chain_broken = False
        self.chain_broken_at = None

        tools = list(LOCAL_TOOLS_SCHEMA)
        tools.extend(mcp_tools_to_openai_schema(mcp_client.list_tools()))
        self.tools_schema = tools

    def _execute_tool(self, name, args):
        # HARD GUARD: если цепочка уже сломана — блокируем любой следующий вызов
        if self.use_guard and self.chain_broken:
            blocked_msg = (
                f"[GUARD: BLOCKED] Цепочка сломана на шаге "
                f"`{self.chain_broken_at}`. Вызов `{name}` заблокирован. "
                f"Не вызывай больше инструментов, объясни пользователю."
            )
            self.tool_calls_log.append({
                "tool": name, "args": args, "raw": blocked_msg,
                "blocked": True,
            })
            return blocked_msg

        raw = self.mcp_client.call_tool(
            name[4:] if name.startswith("mcp_") else name, args
        )
        self.tool_calls_log.append({"tool": name, "args": args, "raw": raw})

        if not self.use_guard:
            return raw

        # Проверяем status в ответе
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

        status = data.get("status")
        if status in ("empty", "error"):
            reason = data.get("reason") or data.get("message") or "—"
            self.chain_broken = True
            self.chain_broken_at = name
            return (
                f"[GUARD: CHAIN_BROKEN] Шаг `{name}` вернул status={status}. "
                f"Причина: {reason}. "
                f"НЕ ВЫЗЫВАЙ следующие инструменты. Объясни пользователю, "
                f"на каком шаге остановился и почему."
            )
        return raw

    def run(self, user_query):
        self.tool_calls_log = []
        self.chain_broken = False
        self.chain_broken_at = None
        system_prompt = (SYSTEM_PROMPT_STRICT if self.prompt_mode == "strict"
                         else SYSTEM_PROMPT_WEAK)
        messages = [
            {"role": "system", "content": system_prompt},
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
                    args = json.loads(tc.function.arguments)
                    result = self._execute_tool(tc.function.name, args)
                    print(f"    🔧 {tc.function.name}({args}) → "
                          f"{result[:120]}")
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id,
                        "content": result,
                    })
                    # Дополнительная системная инструкция при guard-срабатывании
                    if self.use_guard and result.startswith("[GUARD"):
                        messages.append({
                            "role": "system",
                            "content": "СТОП. Цепочка прервана. Не вызывай "
                                       "больше инструментов. Объясни "
                                       "пользователю, что произошло.",
                        })
                continue

            return msg.content

        return "Не удалось получить ответ."