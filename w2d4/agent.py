# agent.py
import json
from openai import BadRequestError
from config import client, MODEL
from tools import TOOLS_SCHEMA, TOOLS_MAP
from storage import (
    load_history, save_history,
    load_summary, save_summary,
    append_archive, reset_all as storage_reset,
)
from compressor import compress

SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом. "
    "Не используй markdown-разметку: без **, ##, ```, без таблиц."
)

KEEP_RECENT = 10      # сколько сообщений держим «как есть»
COMPRESS_STEP = 10    # после скольких «лишних» сообщений запускаем сжатие


class SimpleAgent:
    def __init__(self, max_iterations=10, use_compression=False,
                 initial_state=None, persist=True):
        self.max_iterations = max_iterations
        self.use_compression = use_compression
        self.persist = persist

        if initial_state is not None:
            self.history = list(initial_state["history"])
            self.summary = initial_state["summary"]
        else:
            self.history = load_history()
            self.summary = load_summary()
            if self.history or self.summary:
                print(f"📂 Загружено: {len(self.history)} сообщений в hot-истории, "
                      f"summary {'есть' if self.summary else 'нет'}.")

        self.session_stats = {
            "calls": 0, "prompt_tokens": 0,
            "completion_tokens": 0, "total_tokens": 0,
        }
        self.compression_stats = {
            "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
        }

    def _build_api_messages(self):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if self.summary:
            messages.append({
                "role": "system",
                "content": f"Резюме предыдущей части диалога:\n{self.summary}",
            })
        messages.extend(self.history)
        return messages

    def reset(self):
        self.history = []
        self.summary = ""
        if self.persist:
            storage_reset()
        print("🧹 Всё очищено: hot-история, summary, архив.")

    def _execute_tool(self, tool_name, tool_args):
        func = TOOLS_MAP.get(tool_name)
        if func is None:
            return f"Ошибка: инструмент '{tool_name}' не найден."
        try:
            return str(func(**tool_args))
        except Exception as e:
            return f"Ошибка выполнения '{tool_name}': {e}"

    def _maybe_compress(self):
        if not self.use_compression:
            return
        if len(self.history) < KEEP_RECENT + COMPRESS_STEP:
            return

        to_compress = self.history[:-KEEP_RECENT]
        self.history = self.history[-KEEP_RECENT:]

        result = compress(self.summary, to_compress)
        self.summary = result["summary"]

        self.compression_stats["calls"] += 1
        self.compression_stats["prompt_tokens"] += result["prompt_tokens"]
        self.compression_stats["completion_tokens"] += result["completion_tokens"]

        if self.persist:
            save_summary(self.summary)
            save_history(self.history)

        print(f"  🗜️  Сжато {len(to_compress)} сообщений "
              f"({result['prompt_tokens']}+{result['completion_tokens']} ток.)")

    def run(self, user_query):
        snapshot_history = list(self.history)
        snapshot_summary = self.summary

        self.history.append({"role": "user", "content": user_query})
        if self.persist:
            save_history(self.history)
            append_archive([{"role": "user", "content": user_query}])

        for iteration in range(1, self.max_iterations + 1):
            api_messages = self._build_api_messages()
            print(f"  [Итерация {iteration}] Отправляю {len(api_messages)} сообщений в модель...")

            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=api_messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto",
                )
            except BadRequestError as e:
                self.history = snapshot_history
                self.summary = snapshot_summary
                if self.persist:
                    save_history(self.history)
                    save_summary(self.summary)
                print("\n" + "─" * 60)
                print("⚠️  API вернул 400 Bad Request.")
                print(f"Причина: {str(e)[:300]}")
                print(f"История откатана до {len(snapshot_history)} сообщений.")
                print("─" * 60 + "\n")
                return None

            usage = response.usage
            self.session_stats["calls"] += 1
            self.session_stats["prompt_tokens"] += usage.prompt_tokens
            self.session_stats["completion_tokens"] += usage.completion_tokens
            self.session_stats["total_tokens"] += usage.total_tokens

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "tool_calls":
                self.history.append(message.model_dump())
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    tool_result = self._execute_tool(tool_name, tool_args)
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })
                if self.persist:
                    save_history(self.history)
                continue

            final_answer = message.content
            self.history.append({"role": "assistant", "content": final_answer})
            if self.persist:
                save_history(self.history)
                append_archive([{"role": "assistant", "content": final_answer}])

            self._maybe_compress()
            return final_answer

        return "Не удалось получить ответ."