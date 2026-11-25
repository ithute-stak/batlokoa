"""Real database tests using synthetic employees and disposable schemas."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from backend.app.staff_attendance import AttendanceAction, AttendanceRejected
from backend.app.staff_attendance_store import AttendanceStore
from backend.app.staff_authorization import VerifiedStaffIdentity
from backend.app.staff_branch_location import ActiveBranch
from backend.app.staff_branch_location_store import BranchLocationStore
from backend.app.staff_geofence import Position

URL = os.getenv("BATLOKOA_LINK_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL URL not configured")


@pytest.fixture
def environment():
    schema = "test_attendance_" + uuid4().hex
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            def connect():
                # Set search_path at connection startup, before any transaction.
                return psycopg.connect(URL, options=f"-c search_path={schema} -c statement_timeout=10000")
            with connect() as conn:
                for name in ("staff_branch_location_schema.sql", "staff_attendance_schema.sql"):
                    conn.execute(Path("backend/app", name).read_text())
            company, branch_id = uuid4(), uuid4()
            branch = ActiveBranch(company, branch_id, True)
            owner = VerifiedStaffIdentity(uuid4(), company, "COMPANY_OWNER",
                                          True, frozenset(), True)
            staff = VerifiedStaffIdentity(uuid4(), company, "LOAN_OFFICER",
                                          True, frozenset({branch_id}))
            position = Position(-29.31, 27.48, 2)
            BranchLocationStore(connect).register(owner, branch, position, fresh=True)
            yield AttendanceStore(connect), connect, staff, branch, position
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def record(environment, action=AttendanceAction.CLOCK_IN, **kwargs):
    store, _, staff, branch, position = environment
    return store.record(staff, branch, position, action,
                        captured_at=kwargs.get("captured_at", datetime.now(timezone.utc)))


def counts(connect):
    with connect() as conn:
        return (
            conn.execute("SELECT count(*) FROM staff_attendance_sessions").fetchone()[0],
            conn.execute("SELECT count(*) FROM staff_attendance_events").fetchone()[0],
        )


def test_clock_in_and_out(environment):
    _, connect, _, _, _ = environment
    session, first, _ = record(environment)
    closed, second, _ = record(environment, AttendanceAction.CLOCK_OUT)
    assert session == closed and second > first
    assert counts(connect) == (1, 2)
    with connect() as conn:
        start, end = conn.execute(
            "SELECT clocked_in_at, clocked_out_at FROM staff_attendance_sessions"
        ).fetchone()
        assert end >= start
        events = conn.execute(
            "SELECT action FROM staff_attendance_events ORDER BY event_id"
        ).fetchall()
        assert events == [("clock_in",), ("clock_out",)]


def test_concurrent_clock_in(environment):
    _, connect, _, _, _ = environment
    barrier = Barrier(2, timeout=10)
    def attempt():
        barrier.wait()
        try:
            record(environment)
            return "accepted"
        except AttendanceRejected as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt) for _ in range(2)]
        outcomes = [future.result(timeout=20) for future in futures]
    assert sorted(outcomes) == ["ALREADY_CLOCKED_IN", "accepted"]
    assert counts(connect) == (1, 1)


def test_audit_failure_rolls_back_clock_in_and_out(environment):
    _, connect, _, _, _ = environment
    with connect() as conn:
        conn.execute("""ALTER TABLE staff_attendance_events
                        ADD CONSTRAINT test_reject_in CHECK (action <> 'clock_in')""")
    with pytest.raises(psycopg.errors.CheckViolation):
        record(environment)
    assert counts(connect) == (0, 0)
    with connect() as conn:
        conn.execute("ALTER TABLE staff_attendance_events DROP CONSTRAINT test_reject_in")
        conn.execute("""ALTER TABLE staff_attendance_events
                        ADD CONSTRAINT test_reject_out CHECK (action <> 'clock_out')""")
    record(environment)
    with pytest.raises(psycopg.errors.CheckViolation):
        record(environment, AttendanceAction.CLOCK_OUT)
    assert counts(connect) == (1, 1)
    with connect() as conn:
        assert conn.execute(
            "SELECT clocked_out_at FROM staff_attendance_sessions"
        ).fetchone()[0] is None


def test_expired_capture_creates_no_records(environment):
    _, connect, _, _, _ = environment
    with pytest.raises(AttendanceRejected, match="LOCATION_UNVERIFIED"):
        record(environment, captured_at=datetime.now(timezone.utc)-timedelta(minutes=5))
    assert counts(connect) == (0, 0)
