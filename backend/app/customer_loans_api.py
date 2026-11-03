"""Opt-in authenticated customer-loan endpoint.

Nothing in this module provisions credentials or switches on live access.
A trusted application bootstrap must explicitly install ReadRouteConfig only
after an independently reviewed issuer/key policy, customer directory and
borrower-scoped LoanHub credential broker exist.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from jwt import InvalidTokenError
from pydantic import ValidationError

from .identity import validate_access_token
from .loan_reads import LoanReadForbidden, LoanReadService, LoanReadUnavailable
from .loanhub_adapter import LoanHubReadError


@dataclass(frozen=True)
class ReadRouteConfig:
    issuer: str
    audience: str
    public_key: object
    service: LoanReadService


router = APIRouter()


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.get("/api/v1/me/loans", include_in_schema=False)
async def my_loans(request: Request) -> JSONResponse:
    config = getattr(request.app.state, "loan_read_config", None)
    if not isinstance(config, ReadRouteConfig):
        return error(503, "INTEGRATION_DISABLED", "Financial services are not available in this environment.")

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or token != token.strip():
        return error(401, "UNAUTHENTICATED", "A valid customer session is required.")

    try:
        claims = validate_access_token(
            token, issuer=config.issuer, audience=config.audience,
            public_key=config.public_key,
        )
    except (InvalidTokenError, ValidationError, ValueError, TypeError):
        return error(401, "UNAUTHENTICATED", "A valid customer session is required.")

    try:
        loans = await config.service.list_my_loans(claims=claims)
    except LoanReadForbidden:
        return error(403, "NOT_AUTHORIZED", "Customer access is not authorized.")
    except (LoanReadUnavailable, LoanHubReadError):
        return error(503, "LOAN_SERVICE_UNAVAILABLE", "Loan information is temporarily unavailable.")
    return JSONResponse(
        status_code=200,
        content={"loans": [loan.model_dump(mode="json") for loan in loans]},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
