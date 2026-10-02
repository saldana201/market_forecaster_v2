from pathlib import Path

from market_forecaster.auth.password_policy import (
    MIN_PASSWORD_LENGTH,
    PASSWORD_POLICY_HELP,
    password_policy_issues,
    password_policy_message,
)


ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_UI = ROOT / "market_forecaster" / "ui" / "account.py"


def test_strong_password_passes_policy():
    password = "MarketFlow9!Secure"

    assert password_policy_issues(password) == []
    assert password_policy_message(password) is None


def test_password_policy_requires_length_and_character_classes():
    issues = password_policy_issues("short")

    assert f"at least {MIN_PASSWORD_LENGTH} characters" in issues
    assert "an uppercase letter" in issues
    assert "a number" in issues
    assert "a symbol" in issues


def test_whitespace_does_not_count_as_symbol():
    issues = password_policy_issues("StrongPassword9 ")

    assert "a symbol" in issues


def test_password_policy_help_matches_stronger_account_requirement():
    assert "12 characters" in PASSWORD_POLICY_HELP
    assert "uppercase" in PASSWORD_POLICY_HELP
    assert "lowercase" in PASSWORD_POLICY_HELP
    assert "number" in PASSWORD_POLICY_HELP
    assert "symbol" in PASSWORD_POLICY_HELP


def test_account_ui_applies_policy_to_signup_and_password_change():
    source = ACCOUNT_UI.read_text(encoding="utf-8")

    assert source.count("password_policy_message(") >= 2
    assert source.count("help=PASSWORD_POLICY_HELP") >= 2
