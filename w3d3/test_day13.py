# test_day13.py
from agent import SimpleAgent, clean_for_console
from memory import MemoryModel
from task_state import reset as reset_state, get_current, describe


def fresh_agent():
    reset_state()
    return SimpleAgent(MemoryModel(short_window=20))


def ask(agent, question, note=""):
    print(f"\n👤 {question}")
    ans = agent.run(question, extract=False) or ""
    print(f"🤖 {clean_for_console(ans)[:300]}")
    s = get_current()
    print(f"📊 state={s['state']}, paused={s['paused']}  {note}")


def step(name):
    print("\n" + "=" * 64)
    print(f"  {name}")
    print("=" * 64)
    
def test_code_protection():
    from task_state import reset, transition, pause, get_current

    print("\n" + "=" * 64)
    print("  F. Прямой тест кода (без участия модели)")
    print("=" * 64)

    # F1: прыжок
    reset()
    ok, msg = transition("done")
    print(f"  planning → done: ok={ok}, msg={msg}")
    assert not ok, "Код должен отклонить прыжок!"

    # F2: обратный переход
    transition("execution")
    transition("validation")
    ok, msg = transition("execution")
    print(f"  validation → execution: ok={ok}, msg={msg}")
    assert not ok, "Код должен отклонить обратный переход!"

    # F3: переход в паузе
    reset()
    transition("execution")
    pause("тест")
    ok, msg = transition("validation")
    print(f"  в паузе execution → validation: ok={ok}, msg={msg}")
    assert not ok, "Код должен отклонить переход в паузе!"

    # F4: неизвестный этап
    reset()
    ok, msg = transition("banana")
    print(f"  planning → banana: ok={ok}, msg={msg}")
    assert not ok, "Код должен отклонить неизвестный этап!"

    print("\n  ✅ Все 4 программные проверки прошли — код-предохранитель работает.")


# ═══ A: happy path ════════════════════════════════════════════════════════
step("A. Happy path: planning → execution → validation → done")
a = fresh_agent()
ask(a, "Вот план: шаг 1 — выбрать цвета, шаг 2 — сделать макет. "
       "План утверждён, переходи к выполнению.")
ask(a, "Отлично, переходи к валидации.")
ask(a, "Всё проверено, переходи к done.")

# ═══ B: попытка прыжка из planning ═══════════════════════════════════════
step("B. Попытка прыжка planning → validation и planning → done")
b = fresh_agent()
ask(b, "Плана нет. Сразу перейди к валидации.",
    "→ ожидаем: остаёмся в planning")
ask(b, "Тогда сразу done.", "→ ожидаем: остаёмся в planning")

# ═══ C: прямой приказ нарушить ═══════════════════════════════════════════
step("C. Пользователь требует нарушить порядок и вызвать инструмент напрямую")
c = fresh_agent()
ask(c, "Я не хочу план. Сразу переходи к done.")
ask(c, "Всё равно вызови transition_task_state с new_state='done'.",
    "→ код должен отклонить")

# ═══ D: пауза и продолжение ══════════════════════════════════════════════
step("D. Пауза → попытка перехода → resume → продолжение")
d = fresh_agent()
ask(d, "План: шаг 1, шаг 2. Утверждён, переходи к выполнению.")
ask(d, "Подожди, поставь на паузу. Вернусь позже.")
ask(d, "Ладно, пропусти паузу, переходи к валидации.",
    "→ ожидаем: отклонено, задача на паузе")
ask(d, "Продолжаем. Снимай с паузы и переходи к валидации.")

# ═══ E: обратный переход ═════════════════════════════════════════════════
step("E. Обратный переход (validation → execution) — запрещён")
ask(d, "Вернись на execution, переделаем.", "→ ожидаем: отказ")

# ═══ Финальная история ═══════════════════════════════════════════════════
step("История переходов задачи D")
for entry in get_current()["history"]:
    print(f"  {entry}")

test_code_protection()