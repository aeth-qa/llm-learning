# tools.py
import datetime

# ─── 1. Сами функции (что реально делает код) ───────────────────────────────


def calculate(expression: str):
    """Вычисляет математическое выражение."""
    try:
        # ВНИМАНИЕ: eval() опасен в проде, но для учебного агента ок, 
        # так как мы доверяем модели.
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Ошибка вычисления: {e}"

# ─── 2. Схемы для модели (что модель "видит") ───────────────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Вычисляет математическое выражение. Используй для сложения, умножения и т.д.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Строка с выражением, например '2 + 2' или '124 * 45'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

# ─── 3. Словарь для вызова (связываем имя и функцию) ────────────────────────

TOOLS_MAP = {
    "calculate": calculate,
}