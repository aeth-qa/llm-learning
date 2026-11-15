# agent.py
import json
from config import client, MODEL
from tools import TOOLS_SCHEMA, TOOLS_MAP
from storage import load_history, save_history

SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом. "
    "Не используй markdown-разметку: без **, ##, ```, без таблиц и списков с дефисами."
)


class SimpleAgent:
    def __init__(self, max_iterations=10):
        self.max_iterations = max_iterations
        history = load_history()
        # Свежий system + загруженная история
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
        if history:
            print(f"📂 Загружено {len(history)} сообщений из предыдущей сессии.")

    def reset(self):
        """Сбрасывает историю и файл на диске."""
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
        self.messages.append({"role": "user", "content": user_query})
        save_history(self.messages)  # ← точка сохранения 1

        for iteration in range(1, self.max_iterations + 1):
            print(f"  [Итерация {iteration}] Отправляю {len(self.messages)} сообщений в модель...")

            response = client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
            )

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

                # ← точка сохранения 2: только когда ВСЕ результаты добавлены
                save_history(self.messages)
                continue

            else:
                final_answer = message.content
                self.messages.append({"role": "assistant", "content": final_answer})
                save_history(self.messages)  # ← точка сохранения 3
                return final_answer

        return "Не удалось получить ответ за отведённое количество шагов."