# agent.py
import json
from openai import BadRequestError
from config import client, MODEL
from tools import TOOLS_SCHEMA, TOOLS_MAP
from extractors import extract as extract_memory
from invariants import get_all as get_invariants
from invariant_checker import check_answer as check_invariants

SYSTEM_PROMPT = (
    "Ты — полезный ассистент. Отвечай кратко, простым текстом. "
    "Не используй markdown-разметку: без **, ##, ```, без таблиц."
)


def clean_for_console(text):
    if not text:
        return ""
    return " ".join(str(text).split())


class SimpleAgent:
    def __init__(self, memory, max_iterations=10, show_invariants_in_prompt=True):
        self.memory = memory
        self.max_iterations = max_iterations
        self.show_invariants_in_prompt = show_invariants_in_prompt
        self.session_stats = {"dialog_calls": 0,
                              "dialog_prompt_tokens": 0,
                              "dialog_completion_tokens": 0}
        self.extraction_stats = {"calls": 0,
                                 "prompt_tokens": 0,
                                 "completion_tokens": 0}

    def _system_with_state(self):
        from task_state import get_current, TRANSITIONS, EXPECTED_ACTION

        s = get_current()
        allowed = TRANSITIONS.get(s["state"], [])
        allowed_str = ", ".join(allowed) if allowed else "нет (этап финальный)"

        inv = get_invariants()
        inv_block = "\n".join(f"- {k}: {v}" for k, v in inv.items())

        block = (
            f"\n\n[СОСТОЯНИЕ ЗАДАЧИ]\n"
            f"Этап: {s['state']}{' (ПАУЗА)' if s['paused'] else ''}\n"
            f"Ожидаемое действие: {EXPECTED_ACTION.get(s['state'], '—')}\n"
            f"Допустимые переходы из текущего этапа: [{allowed_str}]\n"
            f"\nПРАВИЛА ПЕРЕХОДОВ:\n"
            f"1. Если этап в списке допустимых — СРАЗУ вызывай transition_task_state.\n"
            f"2. Если этап НЕ в списке — откажи, объясни причину.\n"
            f"3. Если на паузе — сначала resume_task, потом переходи.\n"
            f"4. Список допустимых — авторитетный источник.\n"
        )
        if self.show_invariants_in_prompt:
            block += (
                f"\n[ИНВАРИАНТЫ ПРОЕКТА — НАРУШАТЬ НЕЛЬЗЯ]\n{inv_block}\n"
                f"Если пользователь просит нарушить инвариант — откажи и объясни почему. "
                f"Инварианты можно изменить только явной командой в CLI.\n"
            )
        return SYSTEM_PROMPT + block

    def _execute_tool(self, tool_name, tool_args):
        func = TOOLS_MAP.get(tool_name)
        if func is None:
            return f"Ошибка: инструмент '{tool_name}' не найден."
        try:
            return str(func(**tool_args))
        except Exception as e:
            return f"Ошибка '{tool_name}': {e}"

    def _update_memory(self, user_message):
        flat_long = self.memory._flatten_long()
        nw, lu, np_, usage = extract_memory(
            user_message, self.memory.working, flat_long, self.memory.profile,
        )
        self.memory.replace_working(nw)
        self.memory.apply_facts(lu)
        self.memory.replace_profile(np_)
        self.extraction_stats["calls"] += 1
        self.extraction_stats["prompt_tokens"] += usage["prompt_tokens"]
        self.extraction_stats["completion_tokens"] += usage["completion_tokens"]

    def run(self, user_query, extract=True):
        initial_len = len(self.memory.short)
        if extract:
            self.memory.add_message("user", user_query)
            try:
                self._update_memory(user_query)
            except Exception as e:
                print(f"    ⚠️  Экстрактор: {type(e).__name__}: {str(e)[:80]}")
        else:
            self.memory.short.append({"role": "user", "content": user_query})

        try:
            for iteration in range(1, self.max_iterations + 1):
                api_messages = self.memory.build_api_messages(
                    self._system_with_state()
                )
                try:
                    response = client.chat.completions.create(
                        model=MODEL, messages=api_messages,
                        tools=TOOLS_SCHEMA, tool_choice="auto",
                    )
                except BadRequestError as e:
                    print(f"\n⚠️  400: {str(e)[:250]}\n")
                    return None

                u = response.usage
                self.session_stats["dialog_calls"] += 1
                self.session_stats["dialog_prompt_tokens"] += u.prompt_tokens
                self.session_stats["dialog_completion_tokens"] += u.completion_tokens

                message = response.choices[0].message
                finish_reason = response.choices[0].finish_reason

                if finish_reason == "tool_calls":
                    results = []
                    for tc in message.tool_calls:
                        args = json.loads(tc.function.arguments)
                        r = self._execute_tool(tc.function.name, args)
                        print(f"    🔧 {tc.function.name}({args}) → "
                              f"{clean_for_console(r)[:120]}")
                        results.append(r)
                    self.memory.add_tool_exchange(
                        message.content, message.tool_calls, results
                    )
                    continue

                final = message.content
                if extract:
                    self.memory.add_message("assistant", final)
                    self.memory.trim()
                    check = check_invariants(final, get_invariants())
                    if check["violated"]:
                        refusal = (
                            f"⚠️ Ответ отклонён: нарушение инварианта(ов) "
                            f"{', '.join(check['which'])}. "
                            f"Причина: {check['explanation']}. "
                            f"Инварианты можно изменить только явной командой в CLI."
                        )
                        print(f"    🚫 Чекер отклонил ответ: {check['which']}")
                        return refusal
                return final
            return "Не удалось получить ответ."
        finally:
            if not extract:
                del self.memory.short[initial_len:]