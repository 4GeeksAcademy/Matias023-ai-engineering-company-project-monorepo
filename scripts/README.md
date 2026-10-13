# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

> _Spanish version: [README.es.md](./README.es.md)._

## Nightly telemetry backup and pipeline orchestration

`nightly_export.py` is a standalone system-cron entry point; it is not
scheduled by FastAPI and must not be run from an API lifespan, request, or
background thread. It creates an orchestration row in `job_runs`, writes a
daily telemetry CSV as an audit/recovery backup, and then launches the
existing weekly pipeline as a subprocess. The CSV is **not pipeline input**:
the pipeline continues to read its normal database source.

`job_runs` and `pipeline_runs` have separate responsibilities. `job_runs`
records the nightly orchestration and its `pending -> processing -> completed`
or `pending -> processing -> failed` state. `processing` is the only lock; a
unique `(job_name, target_date)` key plus a conditional atomic update chooses
one winner. A completed date is idempotently skipped; failed rows can retry.
`pipeline_runs` remains owned by the performance ETL and is not used as a lock.

If a process is terminated without running Python exception handlers, a
`processing` row can remain behind. By default, a processing attempt whose
`started_at` is older than **720 minutes (twelve hours)** is eligible for atomic
recovery by the next invocation. Configure a different positive integer with
`NIGHTLY_STALE_LOCK_MINUTES`. A recent processing row remains locked; the
conditional database update allows only one contender to recover a stale row.
Completed rows are never eligible for recovery.

The job is named `nightly_export`. `TARGET_DATE=YYYY-MM-DD` selects the UTC
date for the backup/orchestration. If unset, the date is yesterday in UTC.
The standalone command loads `services/api/.env` before database initialization
using `python-dotenv` with `override=False`: variables already supplied by cron
or the invoking process take precedence. Do not put secrets in the crontab
command; protect the backend `.env` file with appropriate filesystem permissions.
The backup path is `data/raw/telemetry_YYYY-MM-DD.csv`; files already present
are reused, never overwritten. Rows cover `[00:00 UTC on target_date,
00:00 UTC on the next day)`, ordered by timestamp then id. The header is
`id,timestamp,service,event_type,level,value,message,tags`; timestamps are ISO
8601 UTC and tags are stable JSON.

### Manual/safe execution

From repository root, with the backend environment active and a local/test
SQLite URL (never production credentials):

```sh
source services/api/.venv/bin/activate
DATABASE_URL='sqlite:////tmp/nightly-local.db' python scripts/nightly_export.py
TARGET_DATE=2025-01-15 DATABASE_URL='sqlite:////tmp/nightly-local.db' python scripts/nightly_export.py
```

Running the same date again skips both export and pipeline after completion.
Tests under `tests/background/` use isolated temporary SQLite databases and
inject the subprocess runner, so they do not call external services.

### OS crontab

The chosen schedule is `0 2 * * *` (daily at 02:00). This is an implementation
choice, not a 4Geeks-mandated hour. The host's cron timezone must be UTC so the
schedule aligns with the UTC date boundaries; cron itself does not enforce its
timezone. `scripts/install_nightly_cron.sh` detects this checkout's root,
requires `services/api/.venv/bin/python`, preserves unrelated user crontab
entries, and replaces rather than duplicates its marked entry. It logs to
`data/raw/nightly_export.log`.
The process loads the backend `.env` itself, so the crontab does not need a
`DATABASE_URL` assignment or any embedded secret.

```sh
scripts/install_nightly_cron.sh
crontab -l                         # review installed entries
crontab -e                         # edit/remove manually
```

Do not run the installer during tests. To demonstrate concurrency safely, use
the file-backed SQLite shared by both attempts and synchronize contenders at
the atomic acquisition point; the automated test verifies one winner and one
denial without arbitrary sleeps.

Example safe log shapes:

```text
2026-10-13T02:00:00Z level=INFO job_name=nightly_export target_date=2026-10-12 status=processing Acquired processing lock
2026-10-13T02:01:00Z level=INFO job_name=nightly_export target_date=2026-10-12 status=completed Nightly job completed
2026-10-13T02:00:00Z level=INFO job_name=nightly_export target_date=2026-10-12 status=processing Job is already processing or was claimed concurrently; skipping
```
