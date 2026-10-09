# Market Forecaster Supabase Backup / Restore Runbook

Market Forecaster currently uses a Supabase Free-plan project. Supabase recommends
that Free-plan projects regularly export data with the Supabase CLI and keep
off-site backups. Paid Pro/Team/Enterprise projects receive platform-managed daily
backups; PITR is a separate paid add-on.

This runbook provides a compensating backup process until the project moves to a
paid Supabase backup tier.

## Recovery objectives

Initial launch targets:

- Recovery Point Objective (RPO): no more than 24 hours of database changes.
- Recovery Time Objective (RTO): target 4 hours until the first full
  non-production restore drill establishes a measured value.

These are Market Forecaster operating targets, not Supabase service guarantees.

## What the backup contains

The workflow uses the Supabase CLI logical-dump process and creates:

- roles.sql
- schema.sql
- data.sql
- history_schema.sql
- history_data.sql
- manifest.txt
- SHA256SUMS

The Supabase CLI backup format includes supported Auth database data such as
auth.users as part of the logical database export. It does not back up external
configuration such as API keys, JWT secrets, OAuth provider configuration,
custom-domain DNS, Azure App Service settings, GitHub secrets, or Stripe
configuration. Those remain separate infrastructure/configuration recovery items.

Storage objects are also outside the database backup; if Market Forecaster begins
using Supabase Storage for durable customer files, add a separate object-backup
procedure.

## Backup workflow

GitHub Actions workflow:

    .github/workflows/backup_marketforecaster_supabase.yml

Behavior:

- Push that introduces/changes the workflow performs validation only.
- Scheduled runs execute once per day.
- Manual runs are supported.
- Supabase CLI creates logical SQL dumps.
- SHA-256 checksums are generated.
- Files are packed and encrypted with AES-256 symmetric GPG.
- Plaintext SQL files are removed before upload.
- Only the encrypted archive is uploaded as a GitHub Actions artifact.
- Artifact retention is 30 days.

## Required repository secrets

Configure these in:

    GitHub -> Settings -> Secrets and variables -> Actions

### MARKET_FORECASTER_SUPABASE_DB_URL

Use the Supabase **Connect** panel and copy the **Session Pooler** connection
string as recommended by Supabase.

For this project, the pooler username must be:

    postgres.pbttpkbkimqdoilmwryi

Do not use plain `postgres` as the pooler username. The secret must also include
the current database password. If the password contains URL-reserved characters,
use the connection string exactly as supplied/encoded by the Supabase Connect
panel.

Do not paste this value into chat, source control, documentation, screenshots, or
workflow logs.

### MARKET_FORECASTER_BACKUP_PASSPHRASE

Use a long random passphrase dedicated only to backup encryption.

Keep a copy in the OneEight AI Systems password manager or another recovery
location outside GitHub. If both GitHub and the only copy of this passphrase are
lost, the encrypted backups cannot be restored.

## Integrity validation

GitHub Actions workflow:

    .github/workflows/restore_marketforecaster_supabase.yml

Run it manually with:

- backup_run_id = the run ID of a completed backup workflow
- apply_restore = false

This mode:

1. downloads the encrypted backup artifact
2. decrypts it
3. verifies SHA-256 checksums
4. confirms all expected dump files are present
5. removes decrypted SQL from the runner

It does not modify a database.

## Non-production restore drill

A real restore drill requires a separate, disposable/non-production Supabase
database.

Configure:

    MARKET_FORECASTER_SUPABASE_RESTORE_DB_URL

Then run the restore workflow with:

    apply_restore = true

The workflow refuses a target connection string that appears to reference the
production project ref:

    pbttpkbkimqdoilmwryi

The restore uses the Supabase-documented order:

1. roles
2. schema
3. disable triggers with session_replication_role=replica
4. data
5. migration-history schema/data

It then verifies the presence of:

- public.subscriptions
- public.user_api_keys
- public.shared_forecast_contracts
- auth.users

## Restore owner

Primary owner: OneEight AI Systems application owner/administrator.

During an incident:

1. stop or isolate write traffic if continued writes would worsen data loss
2. identify the newest known-good backup
3. validate/decrypt the backup
4. restore into a non-production target first when time allows
5. verify core relations and customer/auth data
6. only then perform/approve production recovery
7. revalidate Supabase Auth, Stripe webhook processing, subscription authority,
   API keys, Forecast Contracts, and Azure application health

## Upgrade path

Before broad public paid launch, preferred production posture is to move Supabase
to a paid tier that includes platform daily backups and leaked-password protection.

PITR is optional and should be added only when the business needs a substantially
smaller RPO and the added cost is justified.

The GitHub logical backup should remain useful even after upgrading because it is
off-platform and independently encrypted.
