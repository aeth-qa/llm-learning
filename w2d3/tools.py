# tools.py
import datetime

# ─── 1. Сами функции (что реально делает код) ───────────────────────────────

def get_current_time():
    """Возвращает текущее время."""
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

def calculate(expression: str):
    """Вычисляет математическое выражение."""
    try:
        # ВНИМАНИЕ: eval() опасен в проде, но для учебного агента ок, 
        # так как мы доверяем модели.
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Ошибка вычисления: {e}"

def convert_currency(amount: float, from_currency: str, to_currency: str):
    """Конвертирует валюту по зашитому курсу."""
    rates = {
        ("USD", "EUR"): 0.92,
        ("EUR", "USD"): 1.09,
        ("USD", "RUB"): 90.0,
        ("RUB", "USD"): 1 / 90.0,
    }
    from_curr = from_currency.upper()
    to_curr = to_currency.upper()
    
    if from_curr == to_curr:
        return str(amount)
        
    rate = rates.get((from_curr, to_curr))
    if rate is None:
        return f"Ошибка: нет курса для {from_curr} -> {to_curr}"
        
    result = amount * rate
    return f"{amount} {from_curr} = {result:.2f} {to_curr}"

# ─── 2. Схемы для модели (что модель "видит") ───────────────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Возвращает текущее время и дату.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
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
    {
        "type": "function",
        "function": {
            "name": "convert_currency",
            "description": "Конвертирует сумму из одной валюты в другую. Курсы зашиты (USD, EUR, RUB).",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Сумма для конвертации"},
                    "from_currency": {"type": "string", "description": "Исходная валюта (например, USD)"},
                    "to_currency": {"type": "string", "description": "Целевая валюта (например, EUR)"},
                },
                "required": ["amount", "from_currency", "to_currency"],
            },
        },
    },
]

# ─── 3. Словарь для вызова (связываем имя и функцию) ────────────────────────

TOOLS_MAP = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "convert_currency": convert_currency,
}