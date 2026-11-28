# mcp_client.py
import asyncio
import threading
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    """Синхронный фасад над асинхронным MCP SDK.

    Внутри держит отдельный поток с event loop, где живёт MCP-сессия.
    Наружу — простые sync-методы: start / list_tools / call_tool / stop.
    """

    def __init__(self, command, args, cwd=None):
        self.command = command
        self.args = args
        self.cwd = cwd
        self._loop = None
        self._thread = None
        self._session = None
        self._tools = []
        self._exit_stack = None

    def start(self, timeout=60):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        future = asyncio.run_coroutine_threadsafe(self._connect(), self._loop)
        future.result(timeout=timeout)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect(self):
        self._exit_stack = AsyncExitStack()

        params = StdioServerParameters(
            command=self.command,
            args=self.args,
            cwd=self.cwd,
        )
        read, write = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        result = await self._session.list_tools()
        self._tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.input_schema,
            }
            for t in result.tools
        ]

    def list_tools(self):
        return list(self._tools)

    def call_tool(self, name, arguments, timeout=30):
        if self._session is None or self._loop is None:
            return "Ошибка: MCP-сессия не активна"
        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments), self._loop
        )
        try:
            result = future.result(timeout=timeout)
        except Exception as e:
            return f"Ошибка MCP-вызова '{name}': {e}"
        parts = []
        for item in result.content:
            if hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "\n".join(parts) if parts else ""

    def stop(self, timeout=10):
        if self._exit_stack is not None and self._loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._exit_stack.aclose(), self._loop
                )
                future.result(timeout=timeout)
            except Exception:
                pass
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=timeout)