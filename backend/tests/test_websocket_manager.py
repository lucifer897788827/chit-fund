import asyncio

import pytest

from app.core.websocket import ConnectionManager, connection_manager


class FakeWebSocket:
    def __init__(self, *, fail_on_send: bool = False):
        self.fail_on_send = fail_on_send
        self.accepted = 0
        self.sent = []

    async def accept(self):
        self.accepted += 1

    async def send_json(self, payload):
        if self.fail_on_send:
            raise RuntimeError("socket disconnected")
        self.sent.append(payload)


def test_connect_and_disconnect_track_clients_by_session():
    async def scenario():
        manager = ConnectionManager()
        websocket = FakeWebSocket()

        await manager.connect(11, websocket)
        assert websocket.accepted == 1
        assert websocket in manager.active_connections[11]

        await manager.disconnect(11, websocket)
        assert 11 not in manager.active_connections

    asyncio.run(scenario())


def test_broadcast_targets_only_one_session_and_prunes_failed_clients():
    async def scenario():
        manager = ConnectionManager()
        healthy = FakeWebSocket()
        failed = FakeWebSocket(fail_on_send=True)
        other_session = FakeWebSocket()

        await manager.connect(11, healthy)
        await manager.connect(11, failed)
        await manager.connect(12, other_session)

        await manager.broadcast(11, {"kind": "room_snapshot", "sessionId": 11})

        assert healthy.sent == [{"kind": "room_snapshot", "sessionId": 11}]
        assert other_session.sent == []
        assert failed not in manager.active_connections.get(11, set())
        assert 12 in manager.active_connections

    asyncio.run(scenario())


def test_targeted_snapshot_and_error_send_to_single_websocket():
    async def scenario():
        manager = ConnectionManager()
        websocket = FakeWebSocket()

        await manager.connect(33, websocket)

        await manager.send_snapshot(33, websocket, {"kind": "snapshot", "sessionId": 33})
        await manager.send_error(33, websocket, {"kind": "error", "message": "bad room"})

        assert websocket.sent == [
            {"kind": "snapshot", "sessionId": 33},
            {"kind": "error", "message": "bad room"},
        ]

    asyncio.run(scenario())


def test_send_snapshot_prunes_failed_socket_and_clears_empty_session_bucket():
    async def scenario():
        manager = ConnectionManager()
        websocket = FakeWebSocket(fail_on_send=True)

        await manager.connect(44, websocket)
        sent = await manager.send_snapshot(44, websocket, {"kind": "snapshot", "sessionId": 44})

        assert sent is False
        assert 44 not in manager.active_connections

    asyncio.run(scenario())


def test_disconnect_is_idempotent_for_unknown_sockets():
    async def scenario():
        manager = ConnectionManager()
        websocket = FakeWebSocket()

        await manager.disconnect(55, websocket)
        assert 55 not in manager.active_connections

    asyncio.run(scenario())
