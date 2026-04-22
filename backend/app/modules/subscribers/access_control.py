from fastapi import HTTPException, status

from app.core.security import CurrentUser, require_owner, require_subscriber
from app.models.chit import GroupMembership
from app.models.user import Subscriber


def require_owner_subscriber_access(current_user: CurrentUser, subscriber: Subscriber) -> Subscriber:
    owner = require_owner(current_user)
    if subscriber.owner_id != owner.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage another owner's subscriber",
        )
    return subscriber


def require_subscriber_profile_access(current_user: CurrentUser, subscriber: Subscriber) -> Subscriber:
    current_subscriber = require_subscriber(current_user)
    if subscriber.id != current_subscriber.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another subscriber's data",
        )
    return subscriber


def require_subscriber_membership_access(
    current_user: CurrentUser,
    membership: GroupMembership,
) -> GroupMembership:
    current_subscriber = require_subscriber(current_user)
    if membership.subscriber_id != current_subscriber.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another subscriber's membership",
        )
    return membership
