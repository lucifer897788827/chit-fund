from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.time import utcnow
from app.models.support import Notification
from app.models.user import User


@dataclass(frozen=True)
class EmailDeliveryResult:
    delivered: bool
    skipped: bool = False
    reason: str | None = None


class NotificationEmailDeliveryService:
    def __init__(
        self,
        *,
        app_name: str,
        smtp_host: str | None,
        smtp_port: int,
        smtp_username: str | None,
        smtp_password: str | None,
        smtp_from_address: str | None,
        smtp_use_tls: bool,
        smtp_use_ssl: bool,
        smtp_timeout_seconds: float,
        smtp_factory: Callable[..., object] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., object] = smtplib.SMTP_SSL,
    ) -> None:
        self.app_name = app_name
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_from_address = smtp_from_address
        self.smtp_use_tls = smtp_use_tls
        self.smtp_use_ssl = smtp_use_ssl
        self.smtp_timeout_seconds = smtp_timeout_seconds
        self.smtp_factory = smtp_factory
        self.smtp_ssl_factory = smtp_ssl_factory

    @classmethod
    def from_settings(
        cls,
        app_settings: Settings | None = None,
        *,
        smtp_factory: Callable[..., object] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., object] = smtplib.SMTP_SSL,
    ) -> "NotificationEmailDeliveryService":
        resolved_settings = app_settings or settings
        return cls(
            app_name=resolved_settings.app_name,
            smtp_host=resolved_settings.smtp_host,
            smtp_port=resolved_settings.smtp_port,
            smtp_username=resolved_settings.smtp_username,
            smtp_password=resolved_settings.smtp_password,
            smtp_from_address=resolved_settings.smtp_from_address,
            smtp_use_tls=resolved_settings.smtp_use_tls,
            smtp_use_ssl=resolved_settings.smtp_use_ssl,
            smtp_timeout_seconds=resolved_settings.smtp_timeout_seconds,
            smtp_factory=smtp_factory,
            smtp_ssl_factory=smtp_ssl_factory,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_address)

    def deliver(self, db: Session, notification: Notification) -> EmailDeliveryResult:
        if notification.channel != "email":
            return EmailDeliveryResult(delivered=False, skipped=True, reason="notification channel is not email")
        if notification.status == "sent":
            return EmailDeliveryResult(delivered=False, skipped=True, reason="notification already sent")
        if not self.enabled:
            return EmailDeliveryResult(delivered=False, skipped=True, reason="smtp is not configured")

        recipient_email = db.scalar(select(User.email).where(User.id == notification.user_id))
        if not recipient_email:
            return EmailDeliveryResult(delivered=False, skipped=True, reason="recipient email is not configured")

        message = self._build_message(recipient_email, notification)
        client = self._create_client()
        try:
            if self.smtp_use_tls and not self.smtp_use_ssl:
                client.starttls(context=ssl.create_default_context())
            if self.smtp_username:
                client.login(self.smtp_username, self.smtp_password or "")
            client.send_message(message)
        finally:
            quit_method = getattr(client, "quit", None)
            if callable(quit_method):
                quit_method()

        notification.status = "sent"
        notification.sent_at = utcnow()
        db.flush()
        return EmailDeliveryResult(delivered=True)

    def _create_client(self):
        if self.smtp_use_ssl:
            return self.smtp_ssl_factory(self.smtp_host, self.smtp_port, timeout=self.smtp_timeout_seconds)
        return self.smtp_factory(self.smtp_host, self.smtp_port, timeout=self.smtp_timeout_seconds)

    def _build_message(self, recipient_email: str, notification: Notification) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = notification.title
        message["From"] = formataddr((self.app_name, self.smtp_from_address or ""))
        message["To"] = recipient_email
        message.set_content(notification.message)
        return message
