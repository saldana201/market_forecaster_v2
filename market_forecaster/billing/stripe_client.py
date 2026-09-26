"""Small Stripe Billing REST adapter.

Uses Stripe-hosted Checkout and Customer Portal so Market Forecaster never
collects or stores card details.
"""
from __future__ import annotations

import json
from urllib import error, parse, request


class BillingError(RuntimeError):
    """Raised when a Stripe billing operation fails."""


class StripeBillingClient:
    def __init__(self, secret_key: str, timeout_seconds: float = 12.0):
        self.secret_key = str(secret_key or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        if not self.secret_key:
            raise BillingError("Stripe secret key is not configured.")

    def _request_json(
        self,
        path: str,
        *,
        method: str,
        fields: dict[str, str] | None = None,
    ) -> dict:
        data = None
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
        }
        if fields is not None:
            data = parse.urlencode(fields).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        req = request.Request(
            f"https://api.stripe.com/v1/{path.lstrip('/')}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                if not isinstance(payload, dict):
                    raise BillingError("Stripe returned an unexpected response.")
                return payload
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = body
            try:
                payload = json.loads(body)
                message = (
                    (payload.get("error") or {}).get("message")
                    or payload.get("message")
                    or body
                )
            except Exception:
                pass
            raise BillingError(f"Stripe request failed: {message}") from exc
        except error.URLError as exc:
            raise BillingError(f"Stripe is unavailable: {exc.reason}") from exc

    def _post(self, path: str, fields: dict[str, str]) -> dict:
        return self._request_json(path, method="POST", fields=fields)

    def _get(self, path: str) -> dict:
        return self._request_json(path, method="GET")

    def retrieve_price(self, price_id: str) -> dict:
        price_id = str(price_id or "").strip()
        if not price_id:
            raise BillingError("Stripe price ID is not configured.")
        return self._get(f"prices/{parse.quote(price_id, safe='')}")

    def create_checkout_session(
        self,
        *,
        user_id: str,
        email: str | None,
        plan: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        fields = {
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": user_id,
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "metadata[user_id]": user_id,
            "metadata[plan]": plan,
            "subscription_data[metadata][user_id]": user_id,
            "subscription_data[metadata][plan]": plan,
            "allow_promotion_codes": "true",
        }
        if email:
            fields["customer_email"] = email
        return self._post("checkout/sessions", fields)

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict:
        return self._post(
            "billing_portal/sessions",
            {
                "customer": customer_id,
                "return_url": return_url,
            },
        )
