# agent.py
import json
from config import client, MODEL
from tools import TOOLS_SCHEMA, TOOLS_MAP

SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом. "
    "Не используй markdown-разметку: без **, ##, ```, без таблиц и списков с дефисами."
)

class SimpleAgent:
    def __init__(self, max_iterations=10):
        self.max_iterations = max_iterations
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _execute_tool(self, tool_name, tool_args):
        """Выполняет Python-функцию по имени и аргументам, возвращает строку."""
        func = TOOLS_MAP.get(tool_name)
        if func is None:
            return f"Ошибка: инструмент '{tool_name}' не найден."
        try:
            result = func(**tool_args)
            return str(result)
        except Exception as e:
            return f"Ошибка выполнения инструмента '{tool_name}': {e}"

    def run(self, user_query):
        """Основной цикл агента. Возвращает финальный текстовый ответ."""
        # 1. Добавляем сообщение пользователя в историю
        self.messages.append({"role": "user", "content": user_query})

        for iteration in range(1, self.max_iterations + 1):
            # 2. Отправляем запрос в LLM с описанием инструментов
            print(f"  [Итерация {iteration}] Отправляю {len(self.messages)} сообщений в модель...")
            response = client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",  # модель сама решает, вызывать ли инструмент
            )

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # 3. Если модель запросила вызов инструментов
            if finish_reason == "tool_calls":
                # Добавляем ответ ассистента (с tool_calls) в историю
                self.messages.append(message.model_dump())

                print(f"  [Итерация {iteration}] Модель запросила {len(message.tool_calls)} вызов(ов):")

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    print(f"    🔧 {tool_name}({tool_args})")

                    # Выполняем функцию
                    tool_result = self._execute_tool(tool_name, tool_args)

                    print(f"    ✅ Результат: {tool_result}")

                    # Добавляем результат в историю как сообщение с ролью "tool"
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })

                continue
            # 4. Если модель вернула обычный текст (finish_reason == "stop")
            else:
                # Добавляем финальный ответ в историю и возвращаем его
                final_answer = message.content
                self.messages.append({"role": "assistant", "content": final_answer})
                return final_answer

        # Если цикл не завершился за max_iterations
        return "Извините, не удалось получить ответ за отведённое количество шагов."