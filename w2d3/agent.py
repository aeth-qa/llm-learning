# agent.py
import json
from openai import BadRequestError
from config import client, MODEL
from tools import TOOLS_SCHEMA, TOOLS_MAP
from storage import load_history, save_history
from token_counter import count_messages_tokens

SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом. "
    "Не используй markdown-разметку: без **, ##, ```, без таблиц и списков с дефисами."
)


class SimpleAgent:
    def __init__(self, max_iterations=10):
        self.max_iterations = max_iterations
        history = load_history()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
        if history:
            print(f"📂 Загружено {len(history)} сообщений из предыдущей сессии.")

        self.session_stats = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def reset(self):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        save_history(self.messages)
        print("🧹 История очищена. Начинаем с чистого листа.")

    def _execute_tool(self, tool_name, tool_args):
        func = TOOLS_MAP.get(tool_name)
        if func is None:
            return f"Ошибка: инструмент '{tool_name}' не найден."
        try:
            return str(func(**tool_args))
        except Exception as e:
            return f"Ошибка выполнения '{tool_name}': {e}"

    def run(self, user_query):
        # Снапшот для отката, если API отклонит запрос
        snapshot = list(self.messages)

        self.messages.append({"role": "user", "content": user_query})
        save_history(self.messages)

        for iteration in range(1, self.max_iterations + 1):
            print(f"  [Итерация {iteration}] Отправляю {len(self.messages)} сообщений в модель...")

            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=self.messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto",
                )
            except BadRequestError as e:
                # Откатываем историю до состояния перед запросом
                self.messages = snapshot
                save_history(self.messages)

                print("\n" + "─" * 60)
                print("⚠️  API вернул 400 Bad Request — запрос отклонён.")
                print("─" * 60)
                print(f"Причина: {str(e)[:350]}")
                print()
                print(f"История откатана до {len(snapshot)} сообщений.")
                print("Агент продолжает работать. Можно задать другой вопрос.")
                print("─" * 60 + "\n")
                return None

            usage = response.usage
            self.session_stats["calls"] += 1
            self.session_stats["prompt_tokens"] += usage.prompt_tokens
            self.session_stats["completion_tokens"] += usage.completion_tokens
            self.session_stats["total_tokens"] += usage.total_tokens

            estimated = count_messages_tokens(self.messages)
            print(f"  [Итерация {iteration}] История: {len(self.messages)} сообщений, "
                  f"~{estimated} ток. (оценка) → API: {usage.prompt_tokens} prompt + "
                  f"{usage.completion_tokens} completion")

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "tool_calls":
                self.messages.append(message.model_dump())
                print(f"  [Итерация {iteration}] Модель запросила {len(message.tool_calls)} вызов(ов):")
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    print(f"    🔧 {tool_name}({tool_args})")
                    tool_result = self._execute_tool(tool_name, tool_args)
                    print(f"    ✅ Результат: {tool_result}")
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })
                save_history(self.messages)
                continue

            else:
                final_answer = message.content
                self.messages.append({"role": "assistant", "content": final_answer})
                save_history(self.messages)
                return final_answer

        return "Не удалось получить ответ за отведённое количество шагов."