from app.modules.notifications.sms import (
    NoOpSmsDeliveryProvider,
    SmsDeliveryResult,
    build_sms_delivery_provider,
    send_sms,
)


def test_sms_delivery_defaults_to_safe_no_op():
    provider = build_sms_delivery_provider()

    assert isinstance(provider, NoOpSmsDeliveryProvider)

    result = provider.send_sms(recipient="+919999999999", message="Auction finalized")

    assert result == SmsDeliveryResult(
        delivered=False,
        provider="noop",
        recipient="+919999999999",
        message="Auction finalized",
        skipped_reason="sms_disabled",
    )


def test_sms_delivery_enabled_without_provider_still_noops():
    provider = build_sms_delivery_provider(enabled=True)

    result = provider.send_sms(recipient="+919999999999", message="Auction finalized")

    assert result.delivered is False
    assert result.provider == "noop"
    assert result.skipped_reason == "sms_provider_not_configured"


def test_send_sms_uses_injected_provider():
    class RecordingProvider:
        def __init__(self):
            self.calls = []

        def send_sms(self, *, recipient: str, message: str) -> SmsDeliveryResult:
            self.calls.append((recipient, message))
            return SmsDeliveryResult(
                delivered=True,
                provider="test-provider",
                recipient=recipient,
                message=message,
            )

    provider = RecordingProvider()

    result = send_sms(recipient="+919999999999", message="Auction finalized", provider=provider)

    assert provider.calls == [("+919999999999", "Auction finalized")]
    assert result.delivered is True
    assert result.provider == "test-provider"
