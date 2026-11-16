# agent.py
import json
from pathlib import Path
from openai import BadRequestError
from config import client, MODEL
from tools import TOOLS_SCHEMA, TOOLS_MAP
from strategies import SYSTEM_PROMPT


class SimpleAgent:
    def __init__(self, strategy, max_iterations=10):
        self.strategy = strategy
        self.max_iterations = max_iterations
        self.session_stats = {
            "dialog_calls": 0,
            "dialog_prompt_tokens": 0,
            "dialog_completion_tokens": 0,
        }

    def _execute_tool(self, tool_name, tool_args):
        func = TOOLS_MAP.get(tool_name)
        if func is None:
            return f"Ошибка: инструмент '{tool_name}' не найден."
        try:
            return str(func(**tool_args))
        except Exception as e:
            return f"Ошибка '{tool_name}': {e}"

    def run(self, user_query):
        self.strategy.add_message("user", user_query)

        for iteration in range(1, self.max_iterations + 1):
            api_messages = self.strategy.get_api_messages(SYSTEM_PROMPT)
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=api_messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto",
                )
            except BadRequestError as e:
                print(f"\n⚠️  400 BadRequest: {str(e)[:250]}\n")
                return None

            usage = response.usage
            self.session_stats["dialog_calls"] += 1
            self.session_stats["dialog_prompt_tokens"] += usage.prompt_tokens
            self.session_stats["dialog_completion_tokens"] += usage.completion_tokens

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "tool_calls":
                self.strategy.add_message(
                    "assistant", message.content,
                    tool_calls=[tc.model_dump() for tc in message.tool_calls],
                )
                for tc in message.tool_calls:
                    result = self._execute_tool(
                        tc.function.name,
                        json.loads(tc.function.arguments),
                    )
                    self.strategy.add_message(
                        "tool", result, tool_call_id=tc.id,
                    )
                continue

            final = message.content
            self.strategy.add_message("assistant", final)
            self.strategy.finalize_turn()
            return final

        return "Не удалось получить ответ."

    def save_checkpoint(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        state = {
            "strategy_name": self.strategy.name,
            "strategy_state": self.strategy.state(),
        }
        Path(path).write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_checkpoint(self, path):
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        if state.get("strategy_name") != self.strategy.name:
            print(f"⚠️  Стратегия в checkpoint ({state.get('strategy_name')}) "
                  f"≠ текущей ({self.strategy.name}).")
        self.strategy.load_state(state.get("strategy_state", {}))