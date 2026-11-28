"""Provision only a fresh, dedicated attendance staging database.

Run as its bootstrap administrator. Passwords are read from separate files,
never printed. No production database or existing attendance schema is accepted.
"""
import os
from pathlib import Path
import psycopg
from psycopg import sql
from .staff_attendance_migrate import install

def main():
    if os.environ.get("BATLOKOA_ATTENDANCE_MIGRATION_ACK") != "FRESH_STAGING_DATABASE_ONLY":
        raise SystemExit("Explicit staging approval required")
    dsn = os.environ["BATLOKOA_ATTENDANCE_MIGRATION_DATABASE_URL"]
    passwords = {}
    for role, variable in (
        ("batlokoa_attendance_gateway", "BATLOKOA_STAGING_GATEWAY_PASSWORD_FILE"),
        ("batlokoa_attendance_worker", "BATLOKOA_STAGING_WORKER_PASSWORD_FILE"),
    ):
        password = Path(os.environ[variable]).read_text().strip()
        if len(password) < 32 or len(password) > 256:
            raise SystemExit("Invalid dedicated password")
        passwords[role] = password
    if len(set(passwords.values())) != 2:
        raise SystemExit("Distinct runtime credentials required")
    def connect():
        return psycopg.connect(dsn, connect_timeout=5)
    try:
        with connect() as conn:
            if conn.execute("SELECT current_database(), current_user").fetchone() != (
                "batlokoa_attendance_stage", "attendance_stage_migrator"
            ):
                raise ValueError("Wrong database or bootstrap identity")
            if conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]:
                raise ValueError("Database is not fresh")
            for role, password in passwords.items():
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)))
            conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        install(connect)
        grants = Path(__file__).with_name("staff_attendance_runtime_grants.sql").read_text()
        with connect() as conn:
            conn.execute(grants)
    except Exception:
        raise SystemExit("Staging provisioning failed; inspect disposable database before retry") from None
    print("Dedicated staging schema and restricted runtime roles provisioned")

if __name__ == "__main__":
    main()
