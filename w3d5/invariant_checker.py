import json, re
from config import client, MODEL

PROMPT = """Ты — жёсткий валидатор инвариантов проекта.
Задача: определить, нарушает ли ОТВЕТ модели хотя бы один инвариант.

ИНВАРИАНТЫ (нельзя нарушать даже частично, даже "для примера", даже в гипотетической форме, даже под предлогом "просто обсудить"):
{invariants}

ОТВЕТ МОДЕЛИ:
\"\"\"{answer}\"\"\"

Нарушением считается:
- Прямое предложение использовать запрещённое (например, MongoDB).
- Рекомендация обойти ограничение.
- Согласие с просьбой нарушить инвариант.
- Описание "как бы работало с MongoDB" как варианта для этого проекта.
- Увеличение бюджета выше 247 300 в любом виде (не как цитата инварианта).
- Добавление доставки/лояльности в MVP.

НЕ является нарушением:
- Цитирование инварианта с целью отказа («нельзя MongoDB, потому что…»).
- Общее объяснение MongoDB как технологии ВНЕ контекста проекта (только если явно оговорено «для другого проекта»).

Ответь ТОЛЬКО JSON:
{{"violated": true|false, "which": ["INV-001", ...], "explanation": "кратко что именно нарушено"}}
"""


def check_answer(answer, invariants):
    if not answer or not answer.strip():
        return {"violated": False, "which": [], "explanation": "пустой ответ"}
    inv_text = "\n".join(f"- {k}: {v}" for k, v in invariants.items())
    prompt = PROMPT.format(invariants=inv_text, answer=answer)
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = r.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return {
            "violated": bool(data.get("violated")),
            "which": data.get("which", []),
            "explanation": data.get("explanation", ""),
            "usage": {"pt": r.usage.prompt_tokens, "ct": r.usage.completion_tokens},
        }
    except Exception as e:
        return {
            "violated": True,
            "which": ["CHECKER_ERROR"],
            "explanation": f"{type(e).__name__}: {str(e)[:100]}",
        }