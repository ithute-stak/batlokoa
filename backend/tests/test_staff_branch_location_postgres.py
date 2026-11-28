"""Dedicated branch-location persistence tests against disposable PostgreSQL."""
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from backend.app.staff_authorization import VerifiedStaffIdentity, StaffAccessDenied
from backend.app.staff_branch_location import ActiveBranch
from backend.app.staff_branch_location_store import BranchLocationStore
from backend.app.staff_geofence import Position

URL = os.getenv("BATLOKOA_LINK_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Disposable PostgreSQL URL not configured")


@pytest.fixture
def store():
    schema = "test_staff_geo_" + uuid4().hex
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            def connect():
                conn = psycopg.connect(URL)
                try:
                    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                    return conn
                except Exception:
                    conn.close()
                    raise
            with connect() as conn:
                conn.execute(Path("backend/app/staff_branch_location_schema.sql").read_text())
            yield BranchLocationStore(connect), connect
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_history_and_branch_scope(store):
    service, connect = store
    company = uuid4()
    branch = ActiveBranch(company, uuid4(), True)
    other = ActiveBranch(company, uuid4(), True)
    owner = VerifiedStaffIdentity(uuid4(), company, "COMPANY_OWNER", True,
                                  frozenset(), True)
    staff = VerifiedStaffIdentity(uuid4(), company, "LOAN_OFFICER", True,
                                  frozenset({branch.branch_id}))
    first = Position(-29.31, 27.48, 2)
    second = Position(-29.31001, 27.48, 2)
    assert service.current(owner, branch) is None
    a, _ = service.register(owner, branch, first, fresh=True)
    b, timestamp = service.register(owner, branch, second, fresh=True)
    assert b > a
    revision, location = service.current(staff, branch)
    assert revision == b
    assert location.position == second
    assert location.registered_at == timestamp
    assert location.registered_by == owner.user_id
    assert service.current(owner, other) is None
    with pytest.raises(StaffAccessDenied):
        service.current(staff, other)
    with pytest.raises(StaffAccessDenied):
        service.current(replace(owner, company_id=uuid4()), branch)
    with pytest.raises(StaffAccessDenied):
        service.register(staff, branch, first, fresh=True)
    with pytest.raises(ValueError):
        service.register(owner, branch, first, fresh=False)
    with connect() as conn:
        rows = conn.execute(
            "SELECT revision_id, latitude FROM staff_branch_location_history ORDER BY revision_id"
        ).fetchall()
    assert rows == [(a, first.latitude), (b, second.latitude)]


def test_db_rejects_invalid_coordinates(store):
    _, connect = store
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect() as conn:
            conn.execute(
                """INSERT INTO staff_branch_location_history
                   (company_id, branch_id, latitude, longitude, accuracy_m, registered_by)
                   VALUES (%s,%s,91,27,2,%s)""",
                (uuid4(), uuid4(), uuid4()),
            )
