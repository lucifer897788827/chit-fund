class ConnectionManager:
    async def connect(self, _websocket):
        return None

    async def disconnect(self, _websocket):
        return None

    async def broadcast(self, _channel: str, _payload: dict):
        return None


connection_manager = ConnectionManager()
