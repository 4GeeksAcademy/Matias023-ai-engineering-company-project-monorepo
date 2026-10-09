"""Migrate the telemetry_events table on PostgreSQL/Supabase to match the spec.

Usage:
    python scripts/migrate_telemetry_pg.py

This script:
  1. Drops the existing telemetry_events table (7 rows will be lost — exercise data only).
  2. Recreates it with the correct 8-column schema matching the spec.

Spec schema:
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid()
  timestamp  timestamptz NOT NULL
  service    text NOT NULL
  event_type text NOT NULL
  level      text NOT NULL DEFAULT 'info'
  value      numeric NULL
  message    text NULL
  tags       jsonb NOT NULL DEFAULT '{}'
  + B-tree index on timestamp
  + B-tree index on event_type
  + GIN index on tags
"""

import os
import sys

# Ensure we can import from services/api
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "services", "api", ".env"))

from sqlmodel import Session, create_engine
from sqlalchemy import text

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def main():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is not set. Cannot migrate without a PostgreSQL target.")
        sys.exit(1)

    print(f"Connecting to: {DATABASE_URL.split('@')[-1].split('?')[0]}")

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    with Session(engine) as session:
        # Check existing table
        result = session.exec(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_name = 'telemetry_events')"
            )
        ).first()
        table_exists = result[0] if result else False
        print(f"Table telemetry_events exists: {table_exists}")

        if table_exists:
            # Check row count
            result = session.exec(text("SELECT COUNT(*) FROM telemetry_events")).first()
            count = result[0] if result else 0
            print(f"Current row count: {count}")

            # Show current columns
            print("\nCurrent columns:")
            cols = session.exec(
                text(
                    "SELECT column_name, data_type, is_nullable, "
                    "column_default "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'telemetry_events' "
                    "ORDER BY ordinal_position"
                )
            ).all()
            for col in cols:
                print(f"  {col[0]:15s} {col[1]:20s} nullable={col[2]} default={col[3]}")

            # Drop indexes first
            print("\nDropping indexes...")
            for idx_name in [
                "ix_telemetry_events_tags",
                "ix_telemetry_events_timestamp",
                "ix_telemetry_events_event_type",
            ]:
                try:
                    session.exec(text(f"DROP INDEX IF EXISTS {idx_name}"))
                    print(f"  Dropped {idx_name}")
                except Exception as e:
                    print(f"  Could not drop {idx_name}: {e}")

            session.commit()

        # Drop and recreate table
        print("\nRecreating telemetry_events table...")
        session.exec(
            text(
                """
            DROP TABLE IF EXISTS telemetry_events CASCADE;

            CREATE TABLE telemetry_events (
                id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                timestamp  timestamptz NOT NULL,
                service    text NOT NULL,
                event_type text NOT NULL,
                level      text NOT NULL DEFAULT 'info',
                value      numeric NULL,
                message    text NULL,
                tags       jsonb NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS ix_telemetry_events_timestamp
                ON telemetry_events (timestamp);

            CREATE INDEX IF NOT EXISTS ix_telemetry_events_event_type
                ON telemetry_events (event_type);

            CREATE INDEX IF NOT EXISTS ix_telemetry_events_tags
                ON telemetry_events USING GIN (tags);
            """
            )
        )
        session.commit()

        # Verify
        print("\nVerifying new schema:")
        cols = session.exec(
            text(
                "SELECT column_name, data_type, is_nullable, "
                "column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'telemetry_events' "
                "ORDER BY ordinal_position"
            )
        ).all()
        for col in cols:
            print(f"  {col[0]:15s} {col[1]:20s} nullable={col[2]} default={col[3]}")

        print("\nIndexes:")
        indexes = session.exec(
            text(
                "SELECT indexname, indexdef "
                "FROM pg_indexes "
                "WHERE tablename = 'telemetry_events'"
            )
        ).all()
        for idx in indexes:
            print(f"  {idx[0]:40s} {idx[1]}")

        print("\n✅ Migration complete. Table telemetry_events is now spec-compliant.")


if __name__ == "__main__":
    main()