import pytest
from fastapi import HTTPException

from app.modules.subscribers.schemas import SubscriberCreate
from app.modules.subscribers.validation import validate_subscriber_creation


def test_validate_subscriber_creation_rejects_duplicate_phone(app, db_session):
    payload = SubscriberCreate(
        ownerId=1,
        fullName="Duplicate Phone",
        phone="9999999999",
        email="unique-phone@example.com",
        password="secret123",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_subscriber_creation(db_session, payload)

    assert exc_info.value.status_code == 409


def test_validate_subscriber_creation_rejects_duplicate_email(app, db_session):
    payload = SubscriberCreate(
        ownerId=1,
        fullName="Duplicate Email",
        phone="7777777778",
        email="owner@example.com",
        password="secret123",
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_subscriber_creation(db_session, payload)

    assert exc_info.value.status_code == 409


def test_validate_subscriber_creation_allows_unique_contact_details(app, db_session):
    payload = SubscriberCreate(
        ownerId=1,
        fullName="Unique Subscriber",
        phone="7777777799",
        email="unique-subscriber@example.com",
        password="secret123",
    )

    validated = validate_subscriber_creation(db_session, payload)

    assert validated.phone == payload.phone
    assert validated.email == payload.email
