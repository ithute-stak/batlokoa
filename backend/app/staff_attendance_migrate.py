"""Explicit, atomic attendance schema installation for a fresh staging database.

Run with a migration-only database role, not the gateway or worker role.
Existing/partial installations fail closed; this is not an upgrade mechanism.
"""
import os
from pathlib import Path

import psycopg

SCHEMAS = (
    "staff_branch_location_schema.sql",
    "staff_attendance_schema.sql",
    "staff_attendance_monitor_schema.sql",
    "staff_attendance_access_events_schema.sql",
    "staff_attendance_notification_schema.sql",
    "staff_access_notification_schema.sql",
    "staff_morning_work_roster_schema.sql",
    "staff_morning_reminder_schema.sql",
    "staff_attendance_notification_inbox_schema.sql",
)


def install(connect):
    root = Path(__file__).resolve().parent
    with connect() as conn:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        ("batlokoa:attendance:schema:v1",))
            cur.execute("SET LOCAL search_path TO public")
            cur.execute("SET LOCAL lock_timeout TO '5s'")
            for schema in SCHEMAS:
                cur.execute((root / schema).read_text(encoding="utf-8"))


def main():
    if os.environ.get("BATLOKOA_ATTENDANCE_MIGRATION_ACK") != "FRESH_STAGING_DATABASE_ONLY":
        raise SystemExit("Explicit fresh staging migration approval required")
    dsn = os.environ.get("BATLOKOA_ATTENDANCE_MIGRATION_DATABASE_URL")
    if not dsn:
        raise SystemExit("Dedicated migration database required")
    try:
        install(lambda: psycopg.connect(dsn, connect_timeout=5))
    except Exception:
        raise SystemExit("Attendance migration failed; transaction rolled back") from None
    print("Attendance schema installed; runtime grants and activation not performed")


if __name__ == "__main__":
    main()
