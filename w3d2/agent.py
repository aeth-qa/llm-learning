# agent.py
import json
from openai import BadRequestError
from config import client, MODEL
from tools import TOOLS_SCHEMA, TOOLS_MAP
from extractors import extract as extract_memory

SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом. "
    "Не используй markdown-разметку: без **, ##, ```, без таблиц."
)

def clean_for_console(text):
    """Схлопывает все пробелы/переносы в один пробел."""
    if not text:
        return ""
    return " ".join(str(text).split())

class SimpleAgent:
    def __init__(self, memory, max_iterations=10):
        self.memory = memory
        self.max_iterations = max_iterations
        self.session_stats = {"dialog_calls": 0,
                              "dialog_prompt_tokens": 0,
                              "dialog_completion_tokens": 0}
        self.extraction_stats = {"calls": 0,
                                 "prompt_tokens": 0,
                                 "completion_tokens": 0}

    def _execute_tool(self, tool_name, tool_args):
        func = TOOLS_MAP.get(tool_name)
        if func is None:
            return f"Ошибка: инструмент '{tool_name}' не найден."
        try:
            return str(func(**tool_args))
        except Exception as e:
            return f"Ошибка '{tool_name}': {e}"

    def _update_memory(self, user_message):
        new_working, new_long, new_profile, usage = extract_memory(
            user_message,
            self.memory.working,
            self.memory.long,
            self.memory.profile,
        )
        self.memory.replace_layers(new_working, new_long, new_profile)
        self.extraction_stats["calls"] += 1
        self.extraction_stats["prompt_tokens"] += usage["prompt_tokens"]
        self.extraction_stats["completion_tokens"] += usage["completion_tokens"]

    def run(self, user_query, extract=True):
        if extract:
            self.memory.add_message("user", user_query)
            try:
                self._update_memory(user_query)
            except Exception as e:
                print(f"    ⚠️  Экстрактор: {type(e).__name__}: {str(e)[:80]}")
            probe_message = None
        else:
            probe_message = {"role": "user", "content": user_query}

        try:
            for iteration in range(1, self.max_iterations + 1):
                api_messages = self.memory.build_api_messages(SYSTEM_PROMPT)
                if probe_message is not None:
                    api_messages.append(probe_message)

                try:
                    response = client.chat.completions.create(
                        model=MODEL,
                        messages=api_messages,
                        tools=TOOLS_SCHEMA,
                        tool_choice="auto",
                    )
                except BadRequestError as e:
                    print("\n⚠️  400 BadRequest. Состояние памяти:")
                    for i, m in enumerate(self.memory.short):
                        tc = m.get("tool_calls")
                        tcid = m.get("tool_call_id")
                        print(f"  [{i:>2}] role={m.get('role'):<10} "
                              f"tool_calls={len(tc) if tc else 0} "
                              f"tool_call_id={tcid}")
                    print(f"\nПричина: {str(e)[:250]}\n")
                    return None

                u = response.usage
                self.session_stats["dialog_calls"] += 1
                self.session_stats["dialog_prompt_tokens"] += u.prompt_tokens
                self.session_stats["dialog_completion_tokens"] += u.completion_tokens

                message = response.choices[0].message
                finish_reason = response.choices[0].finish_reason

                if finish_reason == "tool_calls":
                    # Сначала ВСЕ результаты инструментов, потом — атомарно в память
                    tool_results = []
                    for tc in message.tool_calls:
                        tool_args = json.loads(tc.function.arguments)
                        result = self._execute_tool(tc.function.name, tool_args)
                        print(f"    🔧 {tc.function.name}({tool_args}) → "
                              f"{clean_for_console(result)[:120]}")
                        tool_results.append(result)
                    self.memory.add_tool_exchange(
                        message.content, message.tool_calls, tool_results
                    )
                    continue

                final = message.content
                if extract:
                    self.memory.add_message("assistant", final)
                    self.memory.trim()
                return final

            return "Не удалось получить ответ."
        finally:
            pass