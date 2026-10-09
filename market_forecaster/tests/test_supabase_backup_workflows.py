from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / ".github" / "workflows" / "backup_marketforecaster_supabase.yml"
RESTORE = ROOT / ".github" / "workflows" / "restore_marketforecaster_supabase.yml"


def _backup_text() -> str:
    return BACKUP.read_text(encoding="utf-8")


def _restore_text() -> str:
    return RESTORE.read_text(encoding="utf-8")


def test_backup_workflow_uses_supabase_cli_logical_dump():
    text = _backup_text()

    assert "supabase@latest db dump" in text
    assert "--role-only" in text
    assert "--data-only" in text
    assert "--use-copy" in text
    assert "--schema supabase_migrations" in text


def test_backup_workflow_encrypts_before_uploading():
    text = _backup_text()

    assert "gpg" in text
    assert "--cipher-algo AES256" in text
    assert "rm -rf backup" in text
    assert "Upload encrypted off-site backup" in text
    assert "retention-days: 30" in text


def test_backup_workflow_requires_repository_secrets():
    text = _backup_text()

    assert "MARKET_FORECASTER_SUPABASE_DB_URL" in text
    assert "MARKET_FORECASTER_BACKUP_PASSPHRASE" in text
    assert 'echo "::add-mask::$SUPABASE_DB_URL"' in text
    assert 'echo "::add-mask::$BACKUP_PASSPHRASE"' in text


def test_backup_workflow_runs_daily_but_push_only_validates():
    text = _backup_text()

    assert "cron: '41 7 * * *'" in text
    assert "if: github.event_name == 'push'" in text
    assert "if: github.event_name != 'push'" in text


def test_restore_workflow_defaults_to_integrity_validation_only():
    text = _restore_text()

    assert "apply_restore:" in text
    assert "default: false" in text
    assert "sha256sum --check SHA256SUMS" in text
    assert "Database restore: not requested" in text


def test_restore_workflow_refuses_production_project_target():
    text = _restore_text()

    assert "pbttpkbkimqdoilmwryi" in text
    assert "Refusing destructive restore" in text


def test_restore_workflow_requires_explicit_nonproduction_target_to_apply():
    text = _restore_text()

    assert "MARKET_FORECASTER_SUPABASE_RESTORE_DB_URL" in text
    assert "if: inputs.apply_restore" in text
    assert "Restore into non-production Supabase target" in text
    assert "Verify restored Market Forecaster structures" in text


def test_restore_workflow_verifies_core_market_forecaster_structures():
    text = _restore_text()

    for relation in (
        "public.subscriptions",
        "public.user_api_keys",
        "public.shared_forecast_contracts",
        "auth.users",
    ):
        assert relation in text



def test_backup_workflow_validates_session_pooler_username():
    text = _backup_text()

    assert "pooler.supabase.com" in text
    assert 'expected_ref = "pbttpkbkimqdoilmwryi"' in text
    assert 'expected_user = f"postgres.{expected_ref}"' in text
    assert "Copy the Session Pooler string from" in text
    assert "Supabase database URL preflight passed." in text
