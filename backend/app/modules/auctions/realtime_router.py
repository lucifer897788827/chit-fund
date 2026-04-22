from __future__ import annotations

import asyncio
from typing import Any
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import CurrentUser
from app.core.websocket import connection_manager
from app.models.user import Owner, Subscriber, User
from app.modules.auctions.realtime_service import (
    INSTANCE_ID,
    close_auction_event_listener,
    read_next_auction_event,
    subscribe_to_all_auction_events,
)
from app.modules.auctions.service import get_room

router = APIRouter()


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return str(subject)


def _resolve_current_user(db: Session, token: str) -> CurrentUser:
    user_id_text = _decode_token(token)
    try:
        user_id = int(user_id_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    owner = db.scalar(select(Owner).where(Owner.user_id == user.id))
    subscriber = db.scalar(select(Subscriber).where(Subscriber.user_id == user.id))
    return CurrentUser(user=user, owner=owner, subscriber=subscriber)


def _extract_websocket_token(websocket: WebSocket) -> tuple[str | None, str | None]:
    authorization = websocket.headers.get("authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip(), None

    requested_subprotocols = list(websocket.scope.get("subprotocols") or [])
    if len(requested_subprotocols) >= 2 and requested_subprotocols[0] == "access-token":
        token = requested_subprotocols[1].strip()
        if token:
            return token, "access-token"

    if settings.is_dev_profile:
        query_token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
        if query_token:
            return query_token, None

    return None, None


def _build_snapshot_payload(db: Session, session_id: int, current_user: CurrentUser) -> dict[str, Any]:
    room = get_room(db, session_id, current_user)
    return {
        "type": "auction.snapshot",
        "sessionId": session_id,
        "auth": {
            "userId": current_user.user.id,
            "role": current_user.user.role,
            "ownerId": current_user.owner.id if current_user.owner is not None else None,
            "subscriberId": current_user.subscriber.id if current_user.subscriber is not None else None,
        },
        "room": room,
    }


def _should_forward_remote_event(session_id: int, event: dict[str, Any]) -> bool:
    if not isinstance(event, dict):
        return False
    if event.get("sessionId") != session_id:
        return False
    if event.get("sourceInstanceId") == INSTANCE_ID:
        return False
    return True


async def _relay_remote_auction_events(
    session_id: int,
    *,
    stop_event: asyncio.Event | None = None,
    poll_timeout: float = 0.5,
    retry_delay: float = 0.25,
) -> None:
    while stop_event is None or not stop_event.is_set():
        pubsub = subscribe_to_all_auction_events()
        if pubsub is None:
            await asyncio.sleep(retry_delay)
            continue

        try:
            while stop_event is None or not stop_event.is_set():
                event = await asyncio.to_thread(read_next_auction_event, pubsub, poll_timeout, True)
                if event is None or not _should_forward_remote_event(session_id, event):
                    continue
                await connection_manager.broadcast(session_id, jsonable_encoder(event))
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(retry_delay)
        finally:
            close_auction_event_listener(pubsub)


@router.websocket("/ws/auction/{session_id}")
async def auction_realtime_endpoint(
    websocket: WebSocket,
    session_id: int,
    db: Session = Depends(get_db),
):
    token, accepted_subprotocol = _extract_websocket_token(websocket)
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        current_user = _resolve_current_user(db, token)
        snapshot = _build_snapshot_payload(db, session_id, current_user)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    relay_task: asyncio.Task[Any] | None = None
    try:
        connected = await connection_manager.connect(session_id, websocket, subprotocol=accepted_subprotocol)
        if not connected:
            return

        sent = await connection_manager.send_snapshot(session_id, websocket, jsonable_encoder(snapshot))
        if not sent:
            return

        relay_task = asyncio.create_task(_relay_remote_auction_events(session_id))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if relay_task is not None:
            relay_task.cancel()
            with suppress(asyncio.CancelledError):
                await relay_task
        await connection_manager.disconnect(session_id, websocket)
