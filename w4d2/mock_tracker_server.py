# mock_tracker_server.py
"""Mock task tracker MCP server.

Регистрирует 4 инструмента:
  - list_tasks(status)
  - get_task(task_id)
  - create_task(title, assignee, priority)
  - update_task_status(task_id, status)

Состояние — in-memory dict. При перезапуске сервера сбрасывается
(для учебного демо этого достаточно).
"""
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("mock-tracker")

# In-memory хранилище задач
TASKS = {
    "TASK-1": {"id": "TASK-1", "title": "Настроить CI/CD",
               "status": "open", "assignee": "DevOps", "priority": "high"},
    "TASK-2": {"id": "TASK-2", "title": "Написать документацию API",
               "status": "in_progress", "assignee": "TechWriter", "priority": "medium"},
    "TASK-3": {"id": "TASK-3", "title": "Code review модуля оплаты",
               "status": "closed", "assignee": "Senior Dev", "priority": "high"},
}
_next_id = [4]   # счётчик для новых задач


@mcp.tool()
def list_tasks(status: str = "all") -> list[dict]:
    """Вернуть список задач, опционально отфильтрованных по статусу.

    Args:
        status: "open" | "in_progress" | "closed" | "all" (по умолчанию "all")
    """
    if status == "all":
        return list(TASKS.values())
    return [t for t in TASKS.values() if t["status"] == status]


@mcp.tool()
def get_task(task_id: str) -> dict:
    """Вернуть подробности задачи по её ID.

    Args:
        task_id: идентификатор задачи, например "TASK-1"
    """
    if task_id not in TASKS:
        return {"error": f"Задача {task_id} не найдена",
                "available_ids": list(TASKS.keys())}
    return TASKS[task_id]


@mcp.tool()
def create_task(title: str, assignee: str = "unassigned",
                priority: str = "medium") -> dict:
    """Создать новую задачу. Возвращает созданную задачу с присвоенным ID.

    Args:
        title: краткое название задачи
        assignee: на кого назначена (по умолчанию "unassigned")
        priority: "low" | "medium" | "high" (по умолчанию "medium")
    """
    if priority not in ("low", "medium", "high"):
        return {"error": f"Недопустимый приоритет: {priority}"}
    task_id = f"TASK-{_next_id[0]}"
    _next_id[0] += 1
    task = {"id": task_id, "title": title, "status": "open",
            "assignee": assignee, "priority": priority}
    TASKS[task_id] = task
    return task


@mcp.tool()
def update_task_status(task_id: str, status: str) -> dict:
    """Изменить статус задачи.

    Args:
        task_id: идентификатор задачи, например "TASK-1"
        status: "open" | "in_progress" | "closed"
    """
    if task_id not in TASKS:
        return {"error": f"Задача {task_id} не найдена"}
    if status not in ("open", "in_progress", "closed"):
        return {"error": f"Недопустимый статус: {status}"}
    TASKS[task_id]["status"] = status
    return TASKS[task_id]


if __name__ == "__main__":
    mcp.run()   # по умолчанию stdio — то, что нужно для MCPClient