from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models.support import AuditLog


def _serialize_metadata(metadata: Any) -> str | None:
    if metadata is None:
        return None
    return json.dumps(metadata, default=str, separators=(",", ":"), sort_keys=True)


def parse_audit_payload(payload: str | None) -> Any:
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload


def log_audit_event(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | str,
    metadata: Any = None,
    before: Any = None,
    after: Any = None,
    current_user: CurrentUser | None = None,
    actor_user_id: int | None = None,
    owner_id: int | None = None,
) -> AuditLog:
    if current_user is not None:
        if actor_user_id is None:
            actor_user_id = current_user.user.id
        if owner_id is None and current_user.owner is not None:
            owner_id = current_user.owner.id

    audit_log = AuditLog(
        actor_user_id=actor_user_id,
        owner_id=owner_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        metadata_json=_serialize_metadata(metadata),
        before_json=_serialize_metadata(before),
        after_json=_serialize_metadata(after),
    )
    db.add(audit_log)
    db.flush()
    return audit_log
