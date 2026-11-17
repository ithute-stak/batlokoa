"""Phase 54: pure, fail-closed employee authorization boundary.

Inputs MUST come from an independently authenticated, server-side LoanHub staff
context. Never construct StaffIdentity from Flutter fields, HTTP headers, or a
customer/borrower session. This module makes no financial or network calls.
LoanHub remains the final authorization authority on every upstream request.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class StaffPermission(str, Enum):
    VIEW_CLIENTS = "clients:read"
    REGISTER_CLIENT = "clients:create"
    CREATE_APPLICATION = "applications:create"
    PREPARE_OFFER = "offers:create"


# Mirrors only the observed LoanHub lending roles. This is an additional
# restrictive front-door check, NEVER a replacement for LoanHub RBAC.
_LENDING_ROLES = frozenset({
    "COMPANY_OWNER", "COMPANY_ADMIN", "BRANCH_MANAGER",
    "LOAN_OFFICER", "CREDIT_ANALYST",
})


class StaffAccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class VerifiedStaffIdentity:
    """Construct only after trusted LoanHub session and membership verification."""

    user_id: UUID
    company_id: UUID
    role: str
    active: bool
    branch_ids: frozenset[UUID]
    company_wide_scope: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UUID) or not isinstance(self.company_id, UUID):
            raise ValueError("Verified staff identifiers must be UUIDs")
        if not isinstance(self.branch_ids, frozenset) or any(
            not isinstance(branch, UUID) for branch in self.branch_ids
        ):
            raise ValueError("Verified staff branch assignments must be UUIDs")


def require_staff_permission(
    identity: VerifiedStaffIdentity | None,
    *,
    expected_company_id: UUID,
    branch_id: UUID,
    permission: StaffPermission,
) -> None:
    """Deny unless trusted staff identity, company, role and branch all match.

    All write operations must ALSO be checked inside LoanHub with its native
    tenancy, branch, approval and audit controls. No disbursement permission
    exists here. An employee cannot authorize themselves by setting a branch.
    """
    if (
        identity is None
        or not isinstance(expected_company_id, UUID)
        or not isinstance(branch_id, UUID)
        or not isinstance(permission, StaffPermission)
    ):
        raise StaffAccessDenied("Verified staff authorization required")
    if not identity.active or identity.company_id != expected_company_id:
        raise StaffAccessDenied("Inactive or wrong-company staff session")
    if identity.role not in _LENDING_ROLES:
        raise StaffAccessDenied("LoanHub lending role required")
    if identity.company_wide_scope:
        if identity.role not in {"COMPANY_OWNER", "COMPANY_ADMIN"}:
            raise StaffAccessDenied("Company-wide access not permitted for role")
    elif branch_id not in identity.branch_ids:
        raise StaffAccessDenied("Staff member is not assigned to this branch")
    # Explicitly accept only narrowly supported operations.
    if permission not in {
        StaffPermission.VIEW_CLIENTS,
        StaffPermission.REGISTER_CLIENT,
        StaffPermission.CREATE_APPLICATION,
        StaffPermission.PREPARE_OFFER,
    }:
        raise StaffAccessDenied("Operation not supported")
