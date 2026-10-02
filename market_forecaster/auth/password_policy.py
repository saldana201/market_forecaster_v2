"""Application-side password policy for Market Forecaster accounts.

Supabase remains the authentication authority. This policy is an additional
Market Forecaster UI control; it does not replace provider-side leaked-password
checks or provider-side password requirements.
"""
from __future__ import annotations

MIN_PASSWORD_LENGTH = 12

PASSWORD_POLICY_HELP = (
    "Use at least 12 characters with an uppercase letter, lowercase letter, "
    "number, and symbol."
)


def password_policy_issues(password: str) -> list[str]:
    value = str(password or "")
    issues: list[str] = []

    if len(value) < MIN_PASSWORD_LENGTH:
        issues.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if not any(ch.islower() for ch in value):
        issues.append("a lowercase letter")
    if not any(ch.isupper() for ch in value):
        issues.append("an uppercase letter")
    if not any(ch.isdigit() for ch in value):
        issues.append("a number")
    if not any((not ch.isalnum()) and (not ch.isspace()) for ch in value):
        issues.append("a symbol")

    return issues


def password_policy_message(password: str) -> str | None:
    issues = password_policy_issues(password)
    if not issues:
        return None

    if len(issues) == 1:
        missing = issues[0]
    else:
        missing = ", ".join(issues[:-1]) + f", and {issues[-1]}"

    return f"Password must include {missing}."
