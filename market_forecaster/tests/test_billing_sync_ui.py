from market_forecaster.ui.billing import (
    _subscription_sync_details,
    _timestamp_label,
)


def test_timestamp_label_handles_missing_and_iso_values():
    assert _timestamp_label(None) == "Not yet"
    assert _timestamp_label("") == "Not yet"
    assert _timestamp_label("2026-09-27T10:11:12Z") == "2026-09-27 10:11:12 UTC"


def test_subscription_sync_details_exposes_safe_billing_metadata():
    details = _subscription_sync_details(
        {
            "current_period_end": "2026-10-27T10:11:12+00:00",
            "stripe_event_type": "customer.subscription.updated",
            "stripe_event_created_at": "2026-09-27T10:11:12+00:00",
            "cancel_at_period_end": True,
            "stripe_customer_id": "cus_secretish",
            "stripe_subscription_id": "sub_secretish",
        }
    )

    assert details == {
        "period_end": "2026-10-27 10:11:12 UTC",
        "event_type": "customer.subscription.updated",
        "event_time": "2026-09-27 10:11:12 UTC",
        "cancel_at_period_end": "Yes",
    }
    assert "cus_secretish" not in str(details)
    assert "sub_secretish" not in str(details)


def test_subscription_sync_details_has_clear_empty_state():
    assert _subscription_sync_details(None) == {
        "period_end": "Not yet",
        "event_type": "Not yet",
        "event_time": "Not yet",
        "cancel_at_period_end": "No",
    }
