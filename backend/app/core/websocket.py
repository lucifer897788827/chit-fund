from __future__ import annotations

from typing import Any

from starlette.websockets import WebSocketDisconnect


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, set[Any]] = {}

    def _connections_for(self, session_id: int) -> set[Any]:
        return self.active_connections.setdefault(session_id, set())

    def _remove_connection(self, session_id: int, websocket: Any) -> None:
        connections = self.active_connections.get(session_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self.active_connections.pop(session_id, None)

    async def connect(self, session_id: int, websocket: Any, *, subprotocol: str | None = None) -> bool:
        try:
            if subprotocol is not None:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
        except Exception:
            self._remove_connection(session_id, websocket)
            return False

        self._connections_for(session_id).add(websocket)
        return True

    async def disconnect(self, session_id: int, websocket: Any) -> None:
        self._remove_connection(session_id, websocket)

    async def _send(self, websocket: Any, payload: dict[str, Any]) -> bool:
        try:
            await websocket.send_json(payload)
            return True
        except WebSocketDisconnect:
            return False
        except Exception:
            return False

    async def _prune_failed(self, session_id: int, websocket: Any) -> None:
        self._remove_connection(session_id, websocket)

    async def broadcast(self, session_id: int, payload: dict[str, Any]) -> None:
        connections = tuple(self.active_connections.get(session_id, ()))
        for websocket in connections:
            sent = await self._send(websocket, payload)
            if not sent:
                await self._prune_failed(session_id, websocket)

    async def send_snapshot(self, session_id: int, websocket: Any, payload: dict[str, Any]) -> bool:
        if websocket not in self.active_connections.get(session_id, set()):
            return False
        sent = await self._send(websocket, payload)
        if not sent:
            await self._prune_failed(session_id, websocket)
        return sent

    async def send_error(self, session_id: int, websocket: Any, payload: dict[str, Any]) -> bool:
        if websocket not in self.active_connections.get(session_id, set()):
            return False
        sent = await self._send(websocket, payload)
        if not sent:
            await self._prune_failed(session_id, websocket)
        return sent


connection_manager = ConnectionManager()
