# pipeline_server.py
"""MCP-сервер пайплайна: search → summarize → save_to_file.

Каждый инструмент возвращает dict со status: ok | empty | error.
Это контракт — клиент/агент должен проверять status перед следующим шагом.
"""
import json
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("pipeline-server")

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)

# In-memory корпус — «база знаний» про кофе
CORPUS = [
    {"id": "doc1", "title": "История кофе",
     "text": "Кофе появился в Эфиопии. Согласно легенде, пастух Калди "
             "заметил, что его козы становятся бодрее после поедания ягод."},
    {"id": "doc2", "title": "Виды обжарки",
     "text": "Светлая обжарка сохраняет кислотность и фруктовые ноты. "
             "Тёмная обжарка даёт горьковатый, шоколадный вкус."},
    {"id": "doc3", "title": "Способы заваривания",
     "text": "Эспрессо — под давлением 9 бар. V60 — пуровер, "
             "раскрывает кислотность. French press — полное погружение."},
    {"id": "doc4", "title": "Сорта арабики",
     "text": "Arabica и Robusta — основные виды. Арабика мягче, "
             "робуста крепче и содержит больше кофеина."},
    # Триггер-документ, на котором summarize вернёт error
    {"id": "doc_fail", "title": "Секретный документ",
     "text": "Этот документ содержит флаг _trigger_fail, "
             "на котором summarize обязан упасть.",
     "_trigger_fail": True},
]


@mcp.tool()
def search(query: str) -> dict:
    """Найти документы по запросу (поиск по ключевым словам в тексте и title).

    Args:
        query: поисковый запрос, например "кофе" или "обжарка"
    """
    if not query or not query.strip():
        return {"status": "empty", "results": [],
                "reason": "Пустой поисковый запрос"}

    # Триггер: специальный запрос для демонстрации сбоя на шаге 2
    if query.strip().upper() == "FAIL_TRIGGER":
        return {"status": "ok", "results": [CORPUS[-1]], "count": 1}

    q = query.lower()
    matches = [
        doc for doc in CORPUS
        if q in doc["text"].lower() or q in doc["title"].lower()
    ]

    if not matches:
        return {"status": "empty", "results": [],
                "reason": f"Нет совпадений для запроса: {query!r}"}

    return {"status": "ok", "results": matches, "count": len(matches)}


@mcp.tool()
def summarize(texts: list) -> dict:
    """Сделать краткое саммари из списка текстов.

    Args:
        texts: список строк (например, поле text найденных документов)
    """
    if not texts:
        return {"status": "empty", "reason": "Пустой список текстов"}

    # Триггер сбоя: если в исходных документах был _trigger_fail
    joined = " ".join(str(t) for t in texts)
    if "_trigger_fail" in joined or "секретный документ" in joined.lower():
        return {"status": "error",
                "reason": "Summarize failed: unsupported content in input",
                "step": "summarize"}

    # Простое детерминированное саммари (без LLM — так правильно для MCP!)
    words = joined.lower().split()
    top_words = {}
    for w in words:
        w_clean = "".join(c for c in w if c.isalnum())
        if len(w_clean) > 3:
            top_words[w_clean] = top_words.get(w_clean, 0) + 1
    top3 = sorted(top_words.items(), key=lambda x: -x[1])[:3]

    preview = joined[:200].rstrip() + ("..." if len(joined) > 200 else "")

    return {
        "status": "ok",
        "summary": preview,
        "word_count": len(words),
        "top_words": [w for w, _ in top3],
    }


@mcp.tool()
def save_to_file(filename: str, content: str) -> dict:
    """Сохранить контент в файл в папке out/.

    Args:
        filename: имя файла, например "report.txt"
        content: текстовое содержимое
    """
    if not content or not content.strip():
        return {"status": "error",
                "reason": "Нельзя сохранить пустой content",
                "step": "save_to_file"}
    if not filename:
        return {"status": "error", "reason": "Не указан filename"}

    # Защита от path traversal
    safe_name = Path(filename).name
    path = OUT_DIR / safe_name
    path.write_text(content, encoding="utf-8")
    return {
        "status": "ok",
        "saved_to": str(path),
        "size": len(content),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")