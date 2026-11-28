"""Explicitly approved limited read-only employee pilot bootstrap.

Never self-activates. No borrower writes, loan issuance or payments.
This pilot uses one Uvicorn worker and short-lived *volatile* sessions.
It is not a replacement for an audited distributed production session store.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import FastAPI

from .loanhub_staff_verifier import LoanHubStaffVerifier
from .staff_login_routes import StaffLoginConfig, StagingStaffSessionStore
from .loanhub_staff_clients import LoanHubStaffClientDirectory
from .loanhub_registration_review import LoanHubRegistrationReview


MODE = "limited_read_only"
ACK = "VOLATILE_SESSIONS_10_MINUTES_NO_WRITES"
KEY_PATH = "/run/secrets/loanhub_jwt_public.pem"
PUBLIC_ORIGIN = "https://batlokoa.co.ls"
LOANHUB_ORIGIN = "https://api.loanhub.co.ls"


def configure_employee_pilot(app: FastAPI) -> bool:
    """Attach trusted adapters only after every operator-controlled gate passes.

    A malformed opt-in fails startup rather than silently accepting a
    downgraded policy. No external request is made during configuration.
    """
    mode = os.environ.get("BATLOKOA_EMPLOYEE_PILOT_MODE", "")
    if mode == "":
        return False
    if mode != MODE:
        raise ValueError("Unrecognized Batlokoa employee login mode")
    if os.environ.get("BATLOKOA_EMPLOYEE_PILOT_ACK") != ACK:
        raise ValueError("Restricted employee pilot approval is missing")
    public_origin, loanhub_origin = PUBLIC_ORIGIN, LOANHUB_ORIGIN
    attendance_mode = os.environ.get("BATLOKOA_ATTENDANCE_MODE", "")
    if attendance_mode:
        if attendance_mode != "reviewed_staging":
            raise ValueError("Unrecognized attendance staging mode")
        # Fixed isolated staging hostnames, never arbitrary operator URLs.
        # Provision DNS, TLS and a separate LoanHub instance before activation.
        public_origin = "https://attendance-staging.batlokoa.co.ls"
        loanhub_origin = "https://attendance-staging-api.loanhub.co.ls"
        if os.environ.get("BATLOKOA_OWNER_LOGIN_LOANHUB_ACTIVE_MEMBERSHIP") == "true":
            raise ValueError("Unverified owner exception forbidden in attendance staging")
        if os.environ.get("BATLOKOA_STAFF_CREATION_MODE", ""):
            raise ValueError("Staff creation forbidden in attendance staging")
    if os.environ.get("BATLOKOA_EMPLOYEE_PUBLIC_ORIGIN") != public_origin:
        raise ValueError("Public origin must be operator-approved Batlokoa HTTPS")
    if os.environ.get("BATLOKOA_EMPLOYEE_LOANHUB_ORIGIN") != loanhub_origin:
        raise ValueError("LoanHub API origin must be pinned")
    try:
        company = UUID(os.environ["BATLOKOA_EMPLOYEE_COMPANY_ID"])
    except (ValueError, KeyError) as exc:
        raise ValueError("Verified Batlokoa company UUID required") from exc
    if company.int == 0:
        raise ValueError("Batlokoa company UUID cannot be null")

    # This path is a container secret mount supplied by the operator, never
    # a path chosen by an HTTP request or by a visitor.
    path = Path(KEY_PATH)
    status = path.lstat()
    if not stat.S_ISREG(status.st_mode) or status.st_size > 16384 or status.st_size < 100:
        raise ValueError("Invalid trusted public-key mount")
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
        raise ValueError("RSA verification public key required")
    allow_owner = (
        os.environ.get("BATLOKOA_OWNER_LOGIN_LOANHUB_ACTIVE_MEMBERSHIP") == "true"
    )
    verifier = LoanHubStaffVerifier(
        origin=loanhub_origin, public_key=key, batlokoa_company_id=company,
        allow_unverified_company_owner=allow_owner,
    )
    config = StaffLoginConfig(
        public_origin=public_origin,
        loanhub_origin=loanhub_origin,
        verifier=verifier,
        store=StagingStaffSessionStore(max_sessions=100),
    )
    app.state.staff_login_config = config
    # Staff account creation is a distinct privileged release: default off.
    # The existing unverified-owner read-only pilot is never sufficient to
    # create an account; owner_create_member independently re-verifies the
    # owner with allow_unverified_company_owner=False.
    app.state.staff_account_creation_enabled = (
        os.environ.get("BATLOKOA_STAFF_CREATION_MODE") == "verified_owner_reviewed"
        and os.environ.get("BATLOKOA_STAFF_CREATION_ACK")
            == "OWNER_VERIFIED_CSRF_LOANHUB_ACCOUNT_CREATION"
    )
    # Read-only directory has a second independent, explicit activation flag.
    if os.environ.get("BATLOKOA_EMPLOYEE_READONLY_DIRECTORY", "") == "true":
        app.state.staff_client_directory = LoanHubStaffClientDirectory(
            origin=loanhub_origin,
        )
        app.state.staff_client_directory_enabled = True
    # Independent read-only identity review; no client registration writes.
    if os.environ.get("BATLOKOA_STAFF_NATIONAL_ID_CHECK") == "reviewed_read_only":
        if os.environ.get("BATLOKOA_STAFF_NATIONAL_ID_CHECK_ACK") != "POST_BODY_CSRF_NO_CLIENT_WRITES":
            raise ValueError("National ID review operator approval missing")
        app.state.staff_registration_identity_review = LoanHubRegistrationReview(
            origin=loanhub_origin
        )
        app.state.staff_registration_identity_review_enabled = True
    configure_attendance_pilot(app, company=company, env=os.environ, loanhub_origin=loanhub_origin)
    return True


def configure_attendance_pilot(app: FastAPI, *, company: UUID, env,
                               loanhub_origin=LOANHUB_ORIGIN):
    """Explicit staging-only attendance assembly; never migrates or sends on boot."""
    if env.get("BATLOKOA_ATTENDANCE_MODE", "") == "":
        return False
    if (env.get("BATLOKOA_ATTENDANCE_MODE") != "reviewed_staging"
            or env.get("BATLOKOA_ATTENDANCE_ACK") != "STAGING_ATTENDANCE_WRITES_AND_DISCLOSED_MONITORING"
            or env.get("BATLOKOA_ATTENDANCE_COMPANY_ID") != str(company)):
        raise ValueError("Explicit scoped attendance staging approval required")
    from .staff_branch_location_store import BranchLocationStore
    from .staff_attendance_store import AttendanceStore
    from .staff_attendance_monitor_store import AttendanceMonitorStore
    from .staff_attendance_access_store import AttendanceAccessStore
    from .owner_attendance_inbox import OwnerAttendanceInbox
    from .staff_morning_work_roster_store import MorningWorkRosterStore
    from .staff_attendance_notification_inbox import AttendanceNotificationInbox
    from .staff_morning_loanhub_directory import LoanHubMorningDirectory
    import psycopg

    dsn = env.get("BATLOKOA_ATTENDANCE_GATEWAY_DATABASE_URL", "")
    if not dsn:
        raise ValueError("Restricted attendance gateway database required")
    def connect():
        return psycopg.connect(dsn, connect_timeout=5,
            options="-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public")

    flags = {
        "staff_branch_location_enabled": "BATLOKOA_ATTENDANCE_BRANCH_LOCATION",
        "staff_attendance_monitor_enabled": "BATLOKOA_ATTENDANCE_MONITOR",
        "staff_login_location_enabled": "BATLOKOA_ATTENDANCE_LOGIN_LOCATION",
        "staff_logout_audit_enabled": "BATLOKOA_ATTENDANCE_LOGOUT_AUDIT",
        "owner_attendance_inbox_enabled": "BATLOKOA_ATTENDANCE_OWNER_ALERTS",
        "owner_access_inbox_enabled": "BATLOKOA_ATTENDANCE_OWNER_ACCESS",
        "owner_work_roster_enabled": "BATLOKOA_ATTENDANCE_WORK_ROSTER",
        "staff_attendance_receiver_enabled": "BATLOKOA_ATTENDANCE_RECEIVER",
        "staff_attendance_inbox_enabled": "BATLOKOA_ATTENDANCE_INBOX",
    }
    values = {}
    for attr, name in flags.items():
        value = env.get(name, "false")
        if value not in {"true", "false"}:
            raise ValueError("Invalid attendance release flag")
        values[attr] = value == "true"
    state = app.state
    if values["staff_attendance_receiver_enabled"] or values["staff_attendance_inbox_enabled"]:
        directory_token = env.get("BATLOKOA_ATTENDANCE_DIRECTORY_TOKEN", "")
        relay_token = env.get("BATLOKOA_ATTENDANCE_RECEIVER_TOKEN", "")
        if (not 32 <= len(directory_token) <= 4096
                or not 32 <= len(relay_token) <= 4096
                or directory_token == relay_token
                or any(not 33 <= ord(c) <= 126 for c in directory_token + relay_token)):
            raise ValueError("Distinct attendance service credentials required")
        directory = LoanHubMorningDirectory(origin=loanhub_origin,
            company_id=company, token=directory_token)
        state.staff_attendance_notification_inbox = AttendanceNotificationInbox(
            connect, directory, company_id=company)
        state.staff_attendance_receiver_token = relay_token
        state.staff_attendance_receiver_company_id = company

    state.staff_branch_location_store = BranchLocationStore(connect)
    state.staff_attendance_store = AttendanceStore(connect)
    state.staff_attendance_monitor_store = AttendanceMonitorStore(connect)
    state.staff_attendance_access_store = AttendanceAccessStore(connect)
    state.owner_attendance_inbox = OwnerAttendanceInbox(connect)
    state.staff_morning_work_roster_store = MorningWorkRosterStore(connect)
    for attr, enabled in values.items():
        setattr(state, attr, enabled)
    state.staff_attendance_enabled = True
    return True
