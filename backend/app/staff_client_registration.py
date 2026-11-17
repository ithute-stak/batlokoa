"""Phase 60: fail-closed assisted client registration preparation.

LoanHub's real POST /api/v1/company-clients may link an existing global
borrower and update shared borrower profile/debt/bank data. Consequently
this module NEVER makes a write request. It validates a new registration
draft and requires separate identity review before any later write adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from .staff_authorization import (
    VerifiedStaffIdentity, StaffPermission, require_staff_permission,
)


class RegistrationReviewRequired(Exception):
    pass


@dataclass(frozen=True)
class ClientRegistrationDraft:
    first_name: str
    last_name: str
    phone: str
    date_of_birth: date
    gender: str
    district: str
    employment_status: str
    branch_id: UUID
    national_id: str | None = None
    passport_number: str | None = None
    monthly_income: str | None = None
    consent_to_share_profile: bool = False
    consent_to_credit_checks: bool = False


@dataclass(frozen=True)
class RegistrationPreflight:
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    identity_review_required: bool
    can_submit: bool
    reasons: tuple[str, ...]
    # Deliberately excludes national ID, phone, DOB and salary.


def prepare_client_registration(
    *, staff: VerifiedStaffIdentity,
    draft: ClientRegistrationDraft,
) -> RegistrationPreflight:
    if not isinstance(draft, ClientRegistrationDraft):
        raise ValueError("Registration draft required")
    require_staff_permission(
        staff, expected_company_id=staff.company_id,
        branch_id=draft.branch_id,
        permission=StaffPermission.REGISTER_CLIENT,
    )
    for field in (draft.first_name, draft.last_name, draft.district):
        if not isinstance(field, str) or not 1 <= len(field.strip()) <= 100:
            raise ValueError("Invalid required client detail")
    if not isinstance(draft.phone, str) or not 8 <= len(draft.phone.strip()) <= 30:
        raise ValueError("Invalid phone number")
    if not isinstance(draft.date_of_birth, date) or draft.date_of_birth >= date.today():
        raise ValueError("Invalid birth date")
    if not isinstance(draft.gender, str) or not draft.gender.strip():
        raise ValueError("Gender is required")
    if not isinstance(draft.employment_status, str) or not draft.employment_status.strip():
        raise ValueError("Employment status is required")
    if not any([
        isinstance(draft.national_id, str) and bool(draft.national_id.strip()),
        isinstance(draft.passport_number, str) and bool(draft.passport_number.strip()),
    ]):
        raise ValueError("National ID or passport is required")
    for doc in (draft.national_id, draft.passport_number):
        if doc is not None and (not isinstance(doc, str) or len(doc) > 100):
            raise ValueError("Invalid identity reference")
    if draft.monthly_income is not None:
        try:
            amount = Decimal(draft.monthly_income)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("Invalid income") from exc
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValueError("Invalid income")
    if not isinstance(draft.consent_to_share_profile, bool) or not isinstance(
        draft.consent_to_credit_checks, bool
    ):
        raise ValueError("Consent flags must be explicit booleans")
    # The LoanHub create path may update an existing globally matched borrower
    # and its debt history. There is no safe identity review/reservation
    # endpoint connected yet. Never infer "no duplicate" from an empty search.
    return RegistrationPreflight(
        company_id=staff.company_id,
        branch_id=draft.branch_id,
        employee_id=staff.user_id,
        identity_review_required=True,
        can_submit=False,
        reasons=(
            "Trusted identity and legacy record review is required",
            "Client registration write integration remains disabled",
        ),
    )
