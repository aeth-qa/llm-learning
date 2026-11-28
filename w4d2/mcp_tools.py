# mcp_tools.py
def mcp_tools_to_openai_schema(mcp_tools, prefix="mcp_"):
    """Преобразует список MCP-инструментов в формат OpenAI tools."""
    result = []
    for t in mcp_tools:
        result.append({
            "type": "function",
            "function": {
                "name": f"{prefix}{t['name']}",
                "description": t["description"] or f"MCP tool: {t['name']}",
                "parameters": t["input_schema"] or {
                    "type": "object", "properties": {}
                },
            },
        })
    return result