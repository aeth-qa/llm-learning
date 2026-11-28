# multi_mcp_client.py
from mcp_client import MCPClient


class MultiMCPClient:
    """Управляет несколькими MCP-серверами. Маршрутизирует по префиксу."""

    def __init__(self):
        self.clients = {}   # {name: MCPClient}
        self.status = {}    # {name: "ok" | "down: reason"}
        self.prefixes = {}  # {name: prefix}

    def register(self, name, command, args, prefix, cwd=None):
        client = MCPClient(command=command, args=args, cwd=cwd)
        try:
            client.start(timeout=90)
            self.clients[name] = client
            self.prefixes[name] = prefix
            self.status[name] = "ok"
            return True
        except Exception as e:
            self.status[name] = f"down: {type(e).__name__}: {str(e)[:100]}"
            return False

    def get_aggregated_tools(self, allow_per_server=None):
        allow_per_server = allow_per_server or {}
        tools = []
        for name, client in self.clients.items():
            prefix = self.prefixes[name]
            allow = allow_per_server.get(name)
            for t in client.list_tools():
                if allow is not None and t["name"] not in allow:
                    continue
                tools.append({
                    "type": "function",
                    "function": {
                        "name": f"{prefix}{t['name']}",
                        "description": f"[{name}] {t['description']}",
                        "parameters": t["input_schema"] or
                                      {"type": "object", "properties": {}},
                    },
                })
        return tools

    def tool_to_server(self, tool_name):
        for name, prefix in self.prefixes.items():
            if tool_name.startswith(prefix):
                return name, tool_name[len(prefix):]
        return None, None

    def call_routed(self, tool_name, args):
        server, real_name = self.tool_to_server(tool_name)
        if server is None:
            return (f"[ROUTER ERROR] Инструмент '{tool_name}' "
                    f"не привязан ни к одному серверу.")
        if self.status.get(server) != "ok":
            return (f"[SERVER UNAVAILABLE] Сервер `{server}` недоступен "
                    f"({self.status.get(server, '?')}). "
                    f"Инструмент `{real_name}` не может быть вызван.")
        client = self.clients[server]
        try:
            result = client.call_tool(real_name, args)
            if isinstance(result, str) and (
                "Ошибка MCP-вызова" in result or "не активна" in result
            ):
                self.status[server] = f"down: runtime ({result[:80]})"
                return (f"[SERVER UNAVAILABLE] Сервер `{server}` упал: "
                        f"{result[:120]}")
            return result
        except Exception as e:
            self.status[server] = f"down: {type(e).__name__}"
            return (f"[SERVER UNAVAILABLE] Сервер `{server}`: "
                    f"{type(e).__name__}: {str(e)[:120]}")

    def describe_servers(self):
        lines = []
        for name in self.status:
            st = self.status[name]
            if st == "ok":
                prefix = self.prefixes[name]
                names = [f"{prefix}{t['name']}"
                         for t in self.clients[name].list_tools()]
                lines.append(f"- {name}: OK. Инструменты: "
                             f"{', '.join(names[:8])}")
            else:
                lines.append(f"- {name}: НЕДОСТУПЕН ({st})")
        return "\n".join(lines)

    def kill_runtime(self, name):
        """Симулировать падение в середине работы — сессия закрывается,
        но tools остаются в schema, чтобы модель попробовала их вызвать
        и получила [SERVER UNAVAILABLE]."""
        self.status[name] = "down: runtime failure (сессия закрыта)"
        client = self.clients.get(name)
        if client is not None:
            try:
                client.stop()
            except Exception:
                pass

    def stop_all(self):
        for client in list(self.clients.values()):
            try:
                client.stop()
            except Exception:
                pass
        self.clients.clear()