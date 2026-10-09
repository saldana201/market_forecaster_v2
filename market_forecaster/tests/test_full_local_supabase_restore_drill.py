from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "full_local_supabase_restore_drill.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_local_restore_drill_is_manual_and_cost_free():
    text = _text()

    assert "workflow_dispatch:" in text
    assert "backup_run_id:" in text
    assert "supabase@latest init --workdir restore-lab" in text
    assert "supabase@latest start --workdir restore-lab" in text
    assert "MARKET_FORECASTER_SUPABASE_RESTORE_DB_URL" not in text


def test_local_restore_drill_decrypts_and_verifies_backup():
    text = _text()

    assert "MARKET_FORECASTER_BACKUP_PASSPHRASE" in text
    assert "sha256sum --check SHA256SUMS" in text
    assert "Decrypt and verify backup" in text
    assert "roles.sql" in text


def test_local_restore_drill_uses_seeded_platform_roles():
    text = _text()

    assert "production roles.sql remains checksum-verified but is not replayed locally" in text
    assert "--file restored-files/roles.sql" not in text
    assert "roles.local.sql" not in text
    assert "Prepare roles for disposable local restore" not in text


def test_local_restore_drill_restores_application_backup():
    text = _text()

    for file_name in (
        "schema.sql",
        "data.sql",
        "history_schema.sql",
        "history_data.sql",
    ):
        assert f"--file restored-files/{file_name}" in text

    assert "SET session_replication_role = replica" in text


def test_local_restore_drill_verifies_core_data_and_destroys_target():
    text = _text()

    for relation in (
        "public.subscriptions",
        "public.user_api_keys",
        "public.shared_forecast_contracts",
        "auth.users",
    ):
        assert relation in text

    assert "READY forecast contracts" in text
    assert "stop --workdir restore-lab --no-backup" in text
    assert "rm -rf restored-files encrypted-backup restore-lab" in text


def test_local_restore_drill_records_measured_restore_time():
    text = _text()

    assert "RESTORE_RTO_SECONDS" in text
    assert "Measured restore verification time" in text
