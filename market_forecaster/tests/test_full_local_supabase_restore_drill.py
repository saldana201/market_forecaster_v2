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


def test_local_restore_drill_restores_full_logical_backup():
    text = _text()

    for file_name in (
        "roles.sql",
        "schema.sql",
        "data.sql",
        "history_schema.sql",
        "history_data.sql",
    ):
        assert file_name in text

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



def test_local_restore_drill_filters_server_level_role_settings():
    text = _text()

    assert "Prepare roles for disposable local restore" in text
    assert "roles.local.sql" in text
    assert "ALTER ROLE" in text
    assert "server-level role setting statements" in text
    assert "--file restored-files/roles.local.sql" in text



def test_prepare_local_roles_filters_multiline_role_settings(tmp_path):
    from market_forecaster.scripts.prepare_local_restore_roles import prepare_local_roles

    source = tmp_path / "roles.sql"
    target = tmp_path / "roles.local.sql"
    source.write_text(
        """ALTER ROLE postgres SET
    log_min_messages TO 'fatal';
ALTER ROLE authenticator SET statement_timeout TO '8s';
ALTER ROLE postgres WITH LOGIN;
""",
        encoding="utf-8",
    )

    skipped = prepare_local_roles(source, target)
    result = target.read_text(encoding="utf-8")

    assert skipped == 2
    assert "log_min_messages" not in result
    assert "statement_timeout" not in result
    assert "ALTER ROLE postgres WITH LOGIN;" in result


def test_local_restore_workflow_uses_tested_role_filter_helper():
    text = _text()

    assert "market_forecaster.scripts.prepare_local_restore_roles" in text
    assert "restored-files/roles.local.sql" in text
