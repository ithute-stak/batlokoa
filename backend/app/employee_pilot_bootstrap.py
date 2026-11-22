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
    if os.environ.get("BATLOKOA_EMPLOYEE_PUBLIC_ORIGIN") != PUBLIC_ORIGIN:
        raise ValueError("Public origin must be operator-approved Batlokoa HTTPS")
    if os.environ.get("BATLOKOA_EMPLOYEE_LOANHUB_ORIGIN") != LOANHUB_ORIGIN:
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
        origin=LOANHUB_ORIGIN, public_key=key, batlokoa_company_id=company,
        allow_unverified_company_owner=allow_owner,
    )
    config = StaffLoginConfig(
        public_origin=PUBLIC_ORIGIN,
        loanhub_origin=LOANHUB_ORIGIN,
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
            origin=LOANHUB_ORIGIN,
        )
        app.state.staff_client_directory_enabled = True
    # Independent read-only identity review; no client registration writes.
    if os.environ.get("BATLOKOA_STAFF_NATIONAL_ID_CHECK") == "reviewed_read_only":
        if os.environ.get("BATLOKOA_STAFF_NATIONAL_ID_CHECK_ACK") != "POST_BODY_CSRF_NO_CLIENT_WRITES":
            raise ValueError("National ID review operator approval missing")
        app.state.staff_registration_identity_review = LoanHubRegistrationReview(
            origin=LOANHUB_ORIGIN
        )
        app.state.staff_registration_identity_review_enabled = True
    return True
