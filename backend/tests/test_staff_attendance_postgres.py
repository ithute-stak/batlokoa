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
from backend.app.staff_attendance_monitor_store import AttendanceMonitorStore
from backend.app.staff_attendance_monitor import MonitorAlert
from backend.app.staff_geofence import LocationState
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
                for name in ("staff_branch_location_schema.sql", "staff_attendance_schema.sql",
                             "staff_attendance_monitor_schema.sql", "staff_attendance_notification_schema.sql",
                             "staff_attendance_access_events_schema.sql", "staff_access_notification_schema.sql",
                             "staff_morning_work_roster_schema.sql", "staff_morning_reminder_schema.sql",
                             "staff_attendance_notification_inbox_schema.sql"):
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


def test_session_reads_isolate_employee_and_company(environment):
    store, _, staff, branch, position = environment
    first, _, _ = record(environment)
    assert store.read_sessions(staff, open_only=True)[0]["session_id"] == first
    record(environment, AttendanceAction.CLOCK_OUT)
    second, _, _ = record(environment)
    coworker = VerifiedStaffIdentity(uuid4(), staff.company_id, "LOAN_OFFICER",
                                     True, frozenset({branch.branch_id}))
    other_company = VerifiedStaffIdentity(staff.user_id, uuid4(), "COMPANY_OWNER",
                                          True, frozenset(), True)
    third, _, _ = store.record(coworker, branch, position, AttendanceAction.CLOCK_IN,
                               captured_at=datetime.now(timezone.utc))
    assert store.read_sessions(other_company) == []
    assert [row["session_id"] for row in store.read_sessions(coworker)] == [third]
    own = store.read_sessions(staff)
    assert [row["session_id"] for row in own] == [second, first]
    assert own[0]["clocked_out_at"] is None
    assert own[1]["clocked_out_at"] is not None
    assert [row["session_id"] for row in store.read_sessions(staff, open_only=True)] == [second]
    assert [row["session_id"] for row in store.read_sessions(staff, limit=1)] == [second]
    assert [row["session_id"] for row in store.read_sessions(staff, before=second)] == [first]
    assert store.read_sessions(staff, before=first) == []


def test_monitor_scope_replay_and_closed_session(environment):
    _, connect, staff, branch, position = environment
    session, _, _ = record(environment)
    monitor = AttendanceMonitorStore(connect)
    captured = datetime.now(timezone.utc)
    reading, state, alert = monitor.record(staff, branch, session, position,
                                             captured_at=captured)
    assert reading is LocationState.INSIDE and alert is None
    with pytest.raises(AttendanceRejected, match="LOCATION_REPLAYED"):
        monitor.record(staff, branch, session, position, captured_at=captured)
    coworker = VerifiedStaffIdentity(uuid4(), staff.company_id, "LOAN_OFFICER",
                                     True, frozenset({branch.branch_id}))
    with pytest.raises(AttendanceRejected, match="NO_ACTIVE_SESSION"):
        monitor.record(coworker, branch, session, position,
                       captured_at=datetime.now(timezone.utc))
    record(environment, AttendanceAction.CLOCK_OUT)
    with pytest.raises(AttendanceRejected, match="NO_ACTIVE_SESSION"):
        monitor.record(staff, branch, session, position,
                       captured_at=datetime.now(timezone.utc))
    with connect() as conn:
        assert conn.execute("SELECT count(*) FROM staff_attendance_monitor_outbox").fetchone()[0] == 0


def test_monitor_atomic_alert_and_restart(environment, monkeypatch):
    from backend.app import staff_attendance_monitor_store as module
    _, connect, staff, branch, position = environment
    session, _, _ = record(environment)
    start = datetime.now(timezone.utc)
    class Clock(datetime):
        current = start
        @classmethod
        def now(cls, tz=None):
            return cls.current
    monkeypatch.setattr(module, "datetime", Clock)
    outside = Position(position.latitude + 0.001, position.longitude, 2)
    def sample(seconds):
        Clock.current = start + timedelta(seconds=seconds)
        stamp = Clock.fromtimestamp(Clock.current.timestamp(), timezone.utc)
        return AttendanceMonitorStore(connect).record(staff, branch, session, outside,
                                                       captured_at=stamp)
    assert sample(0)[2] is None
    with connect() as conn:
        conn.execute("""ALTER TABLE staff_attendance_monitor_outbox
                        ADD CONSTRAINT test_block_exit CHECK (event_type <> 'reported_outside_perimeter')""")
    with pytest.raises(psycopg.errors.CheckViolation):
        sample(30)
    with connect() as conn:
        assert conn.execute("""SELECT last_confirmed, transition_sequence
            FROM staff_attendance_monitor_state""").fetchone() == ("verified_inside", 0)
        assert conn.execute("SELECT count(*) FROM staff_attendance_monitor_outbox").fetchone()[0] == 0
        conn.execute("ALTER TABLE staff_attendance_monitor_outbox DROP CONSTRAINT test_block_exit")
    assert sample(31)[2] is MonitorAlert.EXIT
    assert sample(60)[2] is None
    with connect() as conn:
        assert conn.execute("""SELECT last_confirmed, transition_sequence
            FROM staff_attendance_monitor_state""").fetchone() == ("verified_outside", 1)
        assert conn.execute("SELECT count(*) FROM staff_attendance_monitor_outbox").fetchone()[0] == 1


@pytest.fixture
def delivery_environment(environment):
    from backend.app.staff_attendance_notification_queue import AttendanceDeliveryQueue
    _, connect, staff, branch, _ = environment
    session, _, _ = record(environment)
    now = datetime.now(timezone.utc)
    with connect() as conn:
        revision = conn.execute(
            "SELECT revision_id FROM staff_branch_location_history"
        ).fetchone()[0]
        alert_id = conn.execute("""INSERT INTO staff_attendance_monitor_outbox
            (session_id, company_id, employee_id, branch_id, location_revision,
             transition_sequence, event_type, observed_at)
            VALUES (%s,%s,%s,%s,%s,1,'reported_outside_perimeter',%s)
            RETURNING alert_id""",
            (session, staff.company_id, staff.user_id, branch.branch_id, revision, now)
        ).fetchone()[0]
    queue = AttendanceDeliveryQueue(connect, company_id=staff.company_id,
                                    release_at=now-timedelta(seconds=1))
    return queue, connect, staff, alert_id, now


def test_delivery_scope_cutoff_and_concurrent_claim(delivery_environment):
    from backend.app.staff_attendance_notification_queue import AttendanceDeliveryQueue
    queue, connect, staff, alert_id, now = delivery_environment
    foreign = AttendanceDeliveryQueue(connect, company_id=uuid4(), release_at=now)
    future = AttendanceDeliveryQueue(connect, company_id=staff.company_id,
                                     release_at=now+timedelta(seconds=1))
    assert foreign.enqueue() == future.enqueue() == 0
    assert queue.enqueue() == 1
    assert queue.enqueue() == 0
    assert foreign.claim() is None and future.claim() is None
    barrier = Barrier(2, timeout=10)
    def claim():
        barrier.wait()
        return queue.claim()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(claim) for _ in range(2)]
        claims = [job.result(timeout=20) for job in jobs]
    accepted = [item for item in claims if item is not None]
    assert len(accepted) == 1
    item = accepted[0]
    assert item.alert_id == alert_id and item.attempts == 1
    with pytest.raises(ValueError):
        foreign.acknowledge(item)
    assert future.acknowledge(item) is False
    assert queue.acknowledge(item) is True
    assert queue.acknowledge(item) is False
    assert queue.claim() is None
    with connect() as conn:
        assert conn.execute("""SELECT d.state, d.delivered_at = a.delivered_at
            FROM staff_attendance_notification_delivery d
            JOIN staff_attendance_monitor_outbox a USING (alert_id)"""
        ).fetchone() == ("delivered", True)


def test_delivery_retry_and_expired_lease_fencing(delivery_environment):
    queue, connect, _, alert_id, _ = delivery_environment
    queue.enqueue()
    first = queue.claim()
    assert queue.fail(first, code="provider_unavailable") is True
    assert queue.claim() is None
    with connect() as conn:
        conn.execute("""UPDATE staff_attendance_notification_delivery
            SET available_at=clock_timestamp()-interval '1 second' WHERE alert_id=%s""",
            (alert_id,))
    second = queue.claim()
    assert second.attempts == 2
    assert second.idempotency_key == first.idempotency_key
    assert queue.acknowledge(first) is False
    with connect() as conn:
        conn.execute("""UPDATE staff_attendance_notification_delivery
            SET lease_until=clock_timestamp()-interval '1 second' WHERE alert_id=%s""",
            (alert_id,))
    third = queue.claim()
    assert third.attempts == 3 and third.lease_token != second.lease_token
    assert queue.fail(second, code="provider_unavailable") is False
    assert queue.fail(third, code="provider_rejected", permanent=True) is True
    assert queue.claim() is None
    with connect() as conn:
        assert conn.execute("""SELECT state, attempts, last_error_code
            FROM staff_attendance_notification_delivery"""
        ).fetchone() == ("dead", 3, "provider_rejected")
        assert conn.execute("SELECT delivered_at FROM staff_attendance_monitor_outbox").fetchone()[0] is None


def test_delivery_expired_final_attempt_is_terminal(delivery_environment):
    queue, connect, _, alert_id, _ = delivery_environment
    queue.enqueue()
    claim = queue.claim()
    with connect() as conn:
        conn.execute("""UPDATE staff_attendance_notification_delivery
            SET attempts=10, lease_until=clock_timestamp()-interval '1 second'
            WHERE alert_id=%s""", (alert_id,))
    assert queue.claim() is None
    assert queue.acknowledge(claim) is False
    with connect() as conn:
        assert conn.execute("""SELECT state, attempts, last_error_code
            FROM staff_attendance_notification_delivery"""
        ).fetchone() == ("dead", 10, "lease_expired")


def test_access_login_requires_fresh_confident_outside_reading(environment):
    from backend.app.staff_attendance_access_store import AttendanceAccessStore
    _, connect, staff, branch, position = environment
    audit = AttendanceAccessStore(connect)
    outside = Position(position.latitude + 0.001, position.longitude, 2)
    uncertain = Position(position.latitude + 0.001, position.longitude, 50)
    assert audit.record_login(staff, uuid4(), branch, position,
        captured_at=datetime.now(timezone.utc)) == (LocationState.INSIDE, False)
    assert audit.record_login(staff, uuid4(), branch, uncertain,
        captured_at=datetime.now(timezone.utc)) == (LocationState.UNVERIFIED, False)
    assert audit.record_login(staff, uuid4(), branch, outside,
        captured_at=datetime.now(timezone.utc)-timedelta(minutes=2)) == (LocationState.UNVERIFIED, False)
    event = uuid4()
    assert audit.record_login(staff, event, branch, outside,
        captured_at=datetime.now(timezone.utc)) == (LocationState.OUTSIDE, True)
    assert audit.record_login(staff, event, branch, outside,
        captured_at=datetime.now(timezone.utc)) == (LocationState.OUTSIDE, False)
    assert counts(connect) == (0, 0)
    with connect() as conn:
        rows = conn.execute("""SELECT event_id, company_id, employee_id, branch_id,
            event_type, location_revision FROM staff_attendance_access_events""").fetchall()
        assert len(rows) == 1
        assert rows[0][:5] == (event, staff.company_id, staff.user_id,
                               branch.branch_id, "reported_login_outside")
        assert rows[0][5] > 0


def test_access_logout_idempotency_and_scope(environment):
    from backend.app.staff_attendance_access_store import AttendanceAccessStore
    from backend.app.staff_authorization import StaffAccessDenied
    _, connect, staff, branch, position = environment
    audit = AttendanceAccessStore(connect)
    event = uuid4()
    assert audit.record_logout(staff, event) is True
    assert audit.record_logout(staff, event) is False
    foreign = VerifiedStaffIdentity(staff.user_id, uuid4(), "LOAN_OFFICER",
                                    True, frozenset({branch.branch_id}))
    with pytest.raises(StaffAccessDenied):
        audit.record_logout(foreign, event)
    with pytest.raises(StaffAccessDenied):
        audit.record_login(foreign, uuid4(), branch, position,
                           captured_at=datetime.now(timezone.utc))
    inactive = VerifiedStaffIdentity(staff.user_id, staff.company_id, "LOAN_OFFICER",
                                     False, staff.branch_ids)
    with pytest.raises(StaffAccessDenied):
        audit.record_logout(inactive, uuid4())
    owner = VerifiedStaffIdentity(uuid4(), staff.company_id, "COMPANY_OWNER",
                                  True, frozenset(), True)
    assert audit.record_logout(owner, uuid4()) is True
    with connect() as conn:
        rows = conn.execute("""SELECT employee_id, branch_id, event_type, location_revision
            FROM staff_attendance_access_events""").fetchall()
        assert set(rows) == {
            (staff.user_id, branch.branch_id, "staff_logged_out", None),
            (owner.user_id, None, "staff_logged_out", None),
        }
    assert counts(connect) == (0, 0)


@pytest.fixture
def access_delivery_environment(environment):
    from backend.app.staff_access_notification_queue import AccessDeliveryQueue
    from backend.app.staff_attendance_access_store import AttendanceAccessStore
    _, connect, staff, branch, position = environment
    now = datetime.now(timezone.utc)
    event = uuid4()
    assert AttendanceAccessStore(connect).record_logout(staff, event)
    queue = AccessDeliveryQueue(connect, company_id=staff.company_id,
                                release_at=now-timedelta(seconds=1))
    return queue, connect, staff, event, now


def test_access_delivery_scope_and_concurrent_claim(access_delivery_environment):
    from backend.app.staff_access_notification_queue import AccessDeliveryQueue
    queue, connect, staff, event, now = access_delivery_environment
    foreign = AccessDeliveryQueue(connect, company_id=uuid4(), release_at=now)
    future = AccessDeliveryQueue(connect, company_id=staff.company_id,
                                 release_at=now+timedelta(days=1))
    assert foreign.enqueue() == future.enqueue() == 0
    assert queue.enqueue() == 1
    assert queue.enqueue() == 0
    assert foreign.claim() is None and future.claim() is None
    barrier = Barrier(2, timeout=10)
    def claim():
        barrier.wait()
        return queue.claim()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(claim) for _ in range(2)]
        claims = [job.result(timeout=20) for job in jobs]
    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    item = claimed[0]
    assert item.event_id == event and item.attempts == 1
    assert item.event_type == "staff_logged_out"
    with pytest.raises(ValueError):
        foreign.acknowledge(item)
    assert future.acknowledge(item) is False
    assert queue.acknowledge(item) is True
    assert queue.acknowledge(item) is False
    assert queue.claim() is None and queue.enqueue() == 0
    with connect() as conn:
        assert conn.execute("""SELECT state, delivered_at IS NOT NULL
            FROM staff_access_notification_delivery WHERE event_id=%s""",
            (event,)).fetchone() == ("delivered", True)
        assert conn.execute("""SELECT event_type FROM staff_attendance_access_events
            WHERE event_id=%s""", (event,)).fetchone() == ("staff_logged_out",)


def test_access_delivery_retry_and_lease_fencing(access_delivery_environment):
    queue, connect, _, event, _ = access_delivery_environment
    queue.enqueue()
    first = queue.claim()
    assert queue.fail(first, code="provider_unavailable") is True
    assert queue.claim() is None
    with connect() as conn:
        conn.execute("""UPDATE staff_access_notification_delivery
            SET available_at=clock_timestamp()-interval '1 second' WHERE event_id=%s""",
            (event,))
    second = queue.claim()
    assert second.attempts == 2
    assert second.idempotency_key == first.idempotency_key
    assert queue.acknowledge(first) is False
    with connect() as conn:
        conn.execute("""UPDATE staff_access_notification_delivery
            SET lease_until=clock_timestamp()-interval '1 second' WHERE event_id=%s""",
            (event,))
    third = queue.claim()
    assert third.attempts == 3 and third.lease_token != second.lease_token
    assert queue.fail(second, code="provider_unavailable") is False
    assert queue.fail(third, code="provider_rejected", permanent=True) is True
    assert queue.claim() is None
    with connect() as conn:
        assert conn.execute("""SELECT state, attempts, last_error_code
            FROM staff_access_notification_delivery""").fetchone() == (
                "dead", 3, "provider_rejected")


def test_access_delivery_expired_final_attempt_is_terminal(access_delivery_environment):
    queue, connect, _, event, _ = access_delivery_environment
    queue.enqueue()
    claim = queue.claim()
    with connect() as conn:
        conn.execute("""UPDATE staff_access_notification_delivery
            SET attempts=10, lease_until=clock_timestamp()-interval '1 second'
            WHERE event_id=%s""", (event,))
    assert queue.claim() is None
    assert queue.acknowledge(claim) is False
    with connect() as conn:
        assert conn.execute("""SELECT state, attempts, last_error_code
            FROM staff_access_notification_delivery""").fetchone() == (
                "dead", 10, "lease_expired")


def test_access_delivery_outside_login_and_branchless_logout(environment):
    from backend.app.staff_access_notification_queue import AccessDeliveryQueue
    from backend.app.staff_attendance_access_store import AttendanceAccessStore
    _, connect, staff, branch, position = environment
    now = datetime.now(timezone.utc)
    store = AttendanceAccessStore(connect)
    outside = Position(position.latitude+0.001, position.longitude, 2)
    login_id, logout_id = uuid4(), uuid4()
    assert store.record_login(staff, login_id, branch, outside,
        captured_at=now) == (LocationState.OUTSIDE, True)
    owner = VerifiedStaffIdentity(uuid4(), staff.company_id, "COMPANY_OWNER",
                                  True, frozenset(), True)
    assert store.record_logout(owner, logout_id)
    queue = AccessDeliveryQueue(connect, company_id=staff.company_id,
                                 release_at=now-timedelta(seconds=1))
    assert queue.enqueue() == 2
    claims = [queue.claim(), queue.claim()]
    by_id = {item.event_id: item for item in claims}
    assert by_id[login_id].event_type == "reported_login_outside"
    assert by_id[login_id].branch_id == branch.branch_id
    assert by_id[logout_id].event_type == "staff_logged_out"
    assert by_id[logout_id].branch_id is None
    assert queue.claim() is None


def test_morning_roster_database_eligibility_and_scope(environment):
    from dataclasses import replace
    from uuid import UUID
    from backend.app.staff_morning_work_roster_store import MorningWorkRosterStore
    from backend.app.staff_morning_roster_source import DatabaseMorningRosterSource
    from backend.app.staff_morning_reminder_queue import MorningReminderClaim
    from backend.app.staff_authorization import StaffAccessDenied

    _, connect, staff, _, _ = environment
    company = staff.company_id
    owner = VerifiedStaffIdentity(uuid4(), company, "COMPANY_OWNER", True, frozenset(), True)
    other_owner = replace(owner, company_id=uuid4())
    coworker = replace(staff, user_id=uuid4())
    off = replace(staff, user_id=uuid4())
    inactive = replace(staff, user_id=uuid4())
    unknown = replace(staff, user_id=uuid4())
    with connect() as conn:
        day = conn.execute("SELECT (clock_timestamp() AT TIME ZONE 'Africa/Maseru')::date").fetchone()[0]
    roster = MorningWorkRosterStore(connect)
    for member, working in [(staff, True), (coworker, True), (off, False), (inactive, True)]:
        assert roster.set_day(owner, member, work_date=day, scheduled_to_work=working)
    assert not roster.set_day(owner, staff, work_date=day, scheduled_to_work=True)
    with pytest.raises(StaffAccessDenied):
        roster.set_day(other_owner, staff, work_date=day, scheduled_to_work=True)
    assert roster.read_day(other_owner, work_date=day)["rows"] == []
    first = roster.read_day(owner, work_date=day, limit=2)
    second = roster.read_day(owner, work_date=day, after=UUID(first["next_after"]), limit=2)
    assert len(first["rows"]) == len(second["rows"]) == 2
    assert second["next_after"] is None
    assert len({row["employee_id"] for row in first["rows"] + second["rows"]}) == 4

    class Directory:
        rows = [staff, coworker, off, replace(inactive, active=False), unknown]
        def employees(self, *, company_id, limit):
            assert company_id == company and limit == 100
            return self.rows

    directory = Directory()
    source = DatabaseMorningRosterSource(connect, directory, company_id=company)
    record(environment)
    rows = {row.employee_id: row for row in source.candidates(company_id=company, work_date=day, limit=100)}
    assert rows[staff.user_id].already_clocked_in is True
    assert rows[coworker.user_id].already_clocked_in is False
    assert rows[off.user_id].scheduled_to_work is False
    assert rows[inactive.user_id].active is False
    assert unknown.user_id not in rows
    claim = MorningReminderClaim(company, coworker.user_id, day, uuid4(), 1)
    assert source.refresh(claim).scheduled_to_work is True
    assert roster.set_day(owner, coworker, work_date=day, scheduled_to_work=False)
    assert source.refresh(claim).scheduled_to_work is False
    with pytest.raises(ValueError):
        source.candidates(company_id=company, work_date=day, limit=1)
    with pytest.raises(ValueError):
        source.refresh(replace(claim, company_id=other_owner.company_id))
    directory.rows = [staff, replace(coworker, company_id=other_owner.company_id)]
    with pytest.raises(ValueError):
        source.candidates(company_id=company, work_date=day, limit=100)


def test_notification_receiver_real_database(environment):
    from backend.app.staff_attendance_notification_inbox import AttendanceNotificationInbox
    from backend.app.staff_attendance_dispatch_worker import DispatchOutcome
    from backend.app.staff_access_notification_queue import AccessDeliveryQueue
    from backend.app.staff_authorization import StaffAccessDenied

    _, connect, staff, _, _ = environment
    company = staff.company_id
    owner = VerifiedStaffIdentity(uuid4(), company, "COMPANY_OWNER", True, frozenset(), True)
    other = VerifiedStaffIdentity(uuid4(), company, "LOAN_OFFICER", True, frozenset())
    foreign = VerifiedStaffIdentity(owner.user_id, uuid4(), "COMPANY_OWNER", True, frozenset(), True)
    class Directory:
        def employees(self, *, company_id, limit):
            assert company_id == company and limit == 100
            return [owner, staff, other]
    inbox = AttendanceNotificationInbox(connect, Directory(), company_id=company)
    event = uuid4()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
    with connect() as conn:
        conn.execute("""INSERT INTO staff_attendance_access_events
            (event_id,company_id,employee_id,event_type)
            VALUES (%s,%s,%s,'staff_logged_out')""", (event,company,staff.user_id))
    queue = AccessDeliveryQueue(connect, company_id=company, release_at=cutoff)
    assert queue.enqueue() == 1
    claim = queue.claim()
    assert claim.event_id == event
    assert inbox.accept_owner_event(event_id=event, access=True, key="wrong") is DispatchOutcome.REJECTED
    for _ in range(2):
        assert inbox.accept_owner_event(event_id=event, access=True,
                    key=claim.idempotency_key) is DispatchOutcome.ACCEPTED
    assert queue.acknowledge(claim)
    rows = inbox.read_notifications(owner)["notifications"]
    assert len(rows) == 1
    assert rows[0]["employee_id"] == str(staff.user_id)
    assert rows[0]["event_type"] == "staff_logged_out"
    assert inbox.read_notifications(staff)["notifications"] == []
    assert inbox.read_notifications(other)["notifications"] == []
    former = VerifiedStaffIdentity(owner.user_id, company, "LOAN_OFFICER", True, frozenset())
    assert inbox.read_notifications(former)["notifications"] == []
    with pytest.raises(StaffAccessDenied):
        inbox.read_notifications(foreign)
    assert inbox.accept_owner_event(event_id=uuid4(), access=True,
                    key=claim.idempotency_key) is DispatchOutcome.REJECTED


def test_runtime_grants_effective_privileges(environment):
    """Use temporary non-login roles; never modify real deployment roles."""
    _, connect, staff, _, _ = environment
    gateway = "test_gateway_" + uuid4().hex
    worker = "test_worker_" + uuid4().hex
    roles = (gateway, worker)
    with connect() as conn:
        schema = conn.execute("SELECT current_schema()").fetchone()[0]
        for role in roles:
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(role)))
        conn.commit()
        try:
            grants = Path("backend/app/staff_attendance_runtime_grants.sql").read_text()
            grants = grants.replace("SCHEMA public TO", f"SCHEMA {schema} TO")
            grants = grants.replace("batlokoa_attendance_gateway", gateway)
            grants = grants.replace("batlokoa_attendance_worker", worker)
            conn.execute(grants)
            conn.commit()
            with conn.transaction():
                conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(gateway)))
                conn.execute("""INSERT INTO staff_attendance_access_events
                    (event_id,company_id,employee_id,event_type)
                    VALUES (%s,%s,%s,'staff_logged_out')""", (uuid4(),staff.company_id,staff.user_id))
                assert conn.execute("SELECT count(*) FROM staff_attendance_access_events").fetchone()[0] == 1
                for statement in ("DELETE FROM staff_attendance_access_events",
                                  "UPDATE staff_branch_location_history SET radius_m=10",
                                  "UPDATE staff_attendance_notification_delivery SET state='dead'"):
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        with conn.transaction():
                            conn.execute(statement)
            with conn.transaction():
                conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(worker)))
                assert conn.execute("SELECT count(*) FROM staff_attendance_access_events").fetchone()[0] == 1
                for statement in ("DELETE FROM staff_attendance_access_events",
                                  "SELECT * FROM staff_branch_location_history",
                                  "UPDATE staff_attendance_sessions SET clocked_out_at=clock_timestamp()",
                                  "SELECT * FROM staff_attendance_notification_inbox"):
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        with conn.transaction():
                            conn.execute(statement)
        finally:
            conn.rollback()
            for role in roles:
                conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            conn.commit()


def test_morning_expired_queue_and_recipient_scope(environment):
    from datetime import time
    from backend.app.staff_morning_reminder import LESOTHO, ReminderCandidate
    from backend.app.staff_morning_reminder_queue import MorningReminderQueue
    from backend.app.staff_attendance_notification_inbox import AttendanceNotificationInbox
    from backend.app.staff_attendance_dispatch_worker import DispatchOutcome

    _, connect, staff, _, _ = environment
    company = staff.company_id
    yesterday = datetime.now(LESOTHO).date() - timedelta(days=1)
    created = datetime.combine(yesterday, time(7), tzinfo=LESOTHO)
    expiry = created + timedelta(minutes=15)
    key = f"batlokoa:morning:{company}:{staff.user_id}:{yesterday.isoformat()}"
    class Directory:
        def employees(self, *, company_id, limit):
            assert company_id == company
            return [staff]
    inbox = AttendanceNotificationInbox(connect, Directory(), company_id=company)
    queue = MorningReminderQueue(connect, company_id=company)
    assert not queue.enqueue(ReminderCandidate(company, staff.user_id, yesterday, True, True, False))
    with connect() as conn:
        conn.execute("""INSERT INTO staff_morning_reminder_delivery
            (company_id,employee_id,work_date,created_at,available_at)
            VALUES (%s,%s,%s,%s,%s)""", (company,staff.user_id,yesterday,created,created))
        conn.execute("""INSERT INTO staff_attendance_notification_inbox
            (company_id,recipient_id,idempotency_key,employee_id,event_type,observed_at,expires_at,created_at)
            VALUES (%s,%s,%s,%s,'morning_reminder',%s,%s,%s)""",
            (company,staff.user_id,key,staff.user_id,created,expiry,created))
    assert queue.claim() is None
    assert inbox.accept_morning(employee_id=staff.user_id,work_date=yesterday,key=key) is DispatchOutcome.REJECTED
    assert inbox.read_notifications(staff)["notifications"] == []
    with connect() as conn:
        assert conn.execute("SELECT state,last_error_code FROM staff_morning_reminder_delivery").fetchone() == ("cancelled","window_closed")
        with pytest.raises(psycopg.errors.UniqueViolation):
            with conn.transaction():
                conn.execute("""INSERT INTO staff_morning_reminder_delivery
                    (company_id,employee_id,work_date,created_at,available_at)
                    VALUES (%s,%s,%s,%s,%s)""", (company,staff.user_id,yesterday,created,created))


def test_morning_successful_delivery_with_disposable_database_clock(environment):
    from datetime import time
    from backend.app.staff_morning_reminder import LESOTHO
    from backend.app.staff_morning_reminder_queue import MorningReminderQueue
    from backend.app.staff_morning_roster_source import DatabaseMorningRosterSource
    from backend.app.staff_morning_reminder_scheduler import MorningReminderScheduler
    from backend.app.staff_morning_reminder_worker import MorningReminderWorker
    from backend.app.staff_attendance_notification_inbox import AttendanceNotificationInbox

    _, original_connect, staff, branch, _ = environment
    company = staff.company_id
    day = datetime.now(LESOTHO).date()
    now = datetime.combine(day, time(7, 1), tzinfo=LESOTHO)
    with original_connect() as conn:
        schema = conn.execute("SELECT current_schema()").fetchone()[0]
        assert schema.startswith("test_attendance_")
        conn.execute(sql.SQL("""CREATE FUNCTION {}.clock_timestamp()
            RETURNS timestamptz LANGUAGE sql VOLATILE AS {}
            """).format(sql.Identifier(schema), sql.Literal(
                "SELECT TIMESTAMPTZ '" + now.isoformat() + "'")))
        already = uuid4()
        for employee in (staff.user_id, already):
            conn.execute("""INSERT INTO staff_morning_work_roster
                (company_id,employee_id,work_date,scheduled_to_work,recorded_by)
                VALUES (%s,%s,%s,true,%s)""", (company,employee,day,staff.user_id))
        conn.execute("""INSERT INTO staff_attendance_sessions
            (company_id,employee_id,branch_id,clocked_in_at)
            VALUES (%s,%s,%s,%s)""", (company,already,branch.branch_id,now-timedelta(minutes=1)))

    def connect():
        conn = original_connect()
        conn.execute(sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
        conn.commit()
        return conn

    coworker = VerifiedStaffIdentity(already, company, "LOAN_OFFICER", True, frozenset())
    class Directory:
        def employees(self, *, company_id, limit):
            assert company_id == company
            return [staff, coworker]
    directory = Directory()
    with connect() as conn:
        assert conn.execute("SELECT clock_timestamp()").fetchone()[0] == now
    queue = MorningReminderQueue(connect, company_id=company)
    source = DatabaseMorningRosterSource(connect, directory, company_id=company)
    inbox = AttendanceNotificationInbox(connect, directory, company_id=company)
    scheduler = MorningReminderScheduler(queue, source, company_id=company,
                                        enabled=True, clock=lambda: now)
    assert scheduler.tick().enqueued == 1
    assert scheduler.tick().enqueued == 0
    class Provider:
        def send(self, claim, *, idempotency_key):
            return inbox.accept_morning(employee_id=claim.employee_id,
                work_date=claim.work_date, key=idempotency_key)
    worker = MorningReminderWorker(queue, source, Provider(), enabled=True)
    assert worker.run_once().accepted == 1
    assert worker.run_once().accepted == 0
    rows = inbox.read_notifications(staff)["notifications"]
    assert len(rows) == 1 and rows[0]["event_type"] == "morning_reminder"
    assert inbox.read_notifications(coworker)["notifications"] == []
    with connect() as conn:
        assert conn.execute("SELECT state FROM staff_morning_reminder_delivery").fetchall() == [("delivered",)]


def test_enabled_receiver_http_to_database(environment):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.staff_attendance_routes import router
    from backend.app.staff_attendance_notification_inbox import AttendanceNotificationInbox
    from backend.app.staff_access_notification_queue import AccessDeliveryQueue
    from backend.app.staff_access_relay_provider import AccessRelayProvider
    from backend.app.staff_attendance_dispatch_worker import DispatchOutcome

    _, connect, staff, _, _ = environment
    company = staff.company_id
    owner = VerifiedStaffIdentity(uuid4(), company, "COMPANY_OWNER", True, frozenset(), True)
    class Directory:
        def employees(self, *, company_id, limit):
            assert company_id == company
            return [owner, staff]
    inbox = AttendanceNotificationInbox(connect, Directory(), company_id=company)
    app = FastAPI()
    app.include_router(router)
    app.state.staff_attendance_enabled = True
    app.state.staff_attendance_receiver_enabled = True
    app.state.staff_attendance_notification_inbox = inbox
    app.state.staff_attendance_receiver_company_id = company
    token = "a" * 48
    app.state.staff_attendance_receiver_token = token
    event = uuid4()
    with connect() as conn:
        conn.execute("""INSERT INTO staff_attendance_access_events
            (event_id,company_id,employee_id,event_type)
            VALUES (%s,%s,%s,'staff_logged_out')""", (event,company,staff.user_id))
    queue = AccessDeliveryQueue(connect, company_id=company,
                                release_at=datetime.now(timezone.utc)-timedelta(minutes=1))
    assert queue.enqueue() == 1
    claim = queue.claim()
    with TestClient(app, base_url="https://relay.test") as client:
        provider = AccessRelayProvider(origin="https://relay.test", company_id=company,
                                       token=token, client=client)
        payload = {"company_id":str(company),"event_id":str(event),
                   "employee_id":str(staff.user_id),"branch_id":None,
                   "event_type":"staff_logged_out","observed_at":claim.observed_at.isoformat()}
        endpoint = "/api/v1/attendance/access-notifications"
        assert client.post(endpoint,json=payload).status_code == 401
        assert client.post(endpoint,json={**payload,"company_id":str(uuid4())},
            headers={"Authorization":"Bearer "+token}).status_code == 403
        app.state.staff_attendance_receiver_enabled = False
        assert client.post(endpoint,json=payload,
            headers={"Authorization":"Bearer "+token}).status_code == 503
        app.state.staff_attendance_receiver_enabled = True
        assert provider.send(claim,idempotency_key=claim.idempotency_key) is DispatchOutcome.ACCEPTED
        assert provider.send(claim,idempotency_key=claim.idempotency_key) is DispatchOutcome.ACCEPTED
    assert queue.acknowledge(claim)
    assert len(inbox.read_notifications(owner)["notifications"]) == 1
