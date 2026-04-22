from fastapi import HTTPException, status

from app.core.security import CurrentUser, require_subscriber
from app.models.external import ExternalChit, ExternalChitEntry
from app.models.user import Subscriber


def require_external_chit_subscriber(current_user: CurrentUser) -> Subscriber:
    return require_subscriber(current_user)


def require_external_chit_subscriber_access(current_user: CurrentUser, subscriber_id: int) -> int:
    current_subscriber = require_subscriber(current_user)
    if subscriber_id != current_subscriber.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another subscriber's external chit data",
        )
    return subscriber_id


def require_external_chit_access(current_user: CurrentUser, external_chit: ExternalChit) -> ExternalChit:
    current_subscriber = require_subscriber(current_user)
    if external_chit.subscriber_id != current_subscriber.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another subscriber's external chit data",
        )
    return external_chit


def require_external_chit_entry_access(
    current_user: CurrentUser,
    external_chit_entry: ExternalChitEntry,
    external_chit: ExternalChit,
) -> ExternalChitEntry:
    require_external_chit_access(current_user, external_chit)
    if external_chit_entry.external_chit_id != external_chit.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another subscriber's external chit entry",
        )
    return external_chit_entry
