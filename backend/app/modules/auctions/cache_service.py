from app.core.redis import redis_client


def cache_room_state(session_id: int, state: dict):
    redis_client.set(f"auction:{session_id}:state", state)
