from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class SmsDeliveryResult:
    delivered: bool
    provider: str
    recipient: str
    message: str
    skipped_reason: str | None = None


class SmsDeliveryProvider(Protocol):
    def send_sms(self, *, recipient: str, message: str) -> SmsDeliveryResult:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class NoOpSmsDeliveryProvider:
    skipped_reason: str = "sms_disabled"

    def send_sms(self, *, recipient: str, message: str) -> SmsDeliveryResult:
        return SmsDeliveryResult(
            delivered=False,
            provider="noop",
            recipient=recipient,
            message=message,
            skipped_reason=self.skipped_reason,
        )


def build_sms_delivery_provider(
    *,
    enabled: bool | None = None,
    provider_name: str | None = None,
) -> SmsDeliveryProvider:
    sms_enabled = settings.sms_enabled if enabled is None else enabled
    sms_provider = settings.sms_provider if provider_name is None else provider_name

    if not sms_enabled:
        return NoOpSmsDeliveryProvider(skipped_reason="sms_disabled")
    if not sms_provider:
        return NoOpSmsDeliveryProvider(skipped_reason="sms_provider_not_configured")
    return NoOpSmsDeliveryProvider(skipped_reason=f"sms_provider_{sms_provider}_not_implemented")


def send_sms(
    *,
    recipient: str,
    message: str,
    provider: SmsDeliveryProvider | None = None,
) -> SmsDeliveryResult:
    sms_provider = provider or build_sms_delivery_provider()
    return sms_provider.send_sms(recipient=recipient, message=message)
