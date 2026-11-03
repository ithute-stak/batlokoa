"""Fail-closed Batlokoa integration gateway.

Public operational probes intentionally reveal no tenant/customer data. All
financial and customer routes remain unavailable until authenticated adapters,
tenant authorization, regulatory and reconciliation controls are implemented.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Batlokoa Integration Gateway",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_UNAVAILABLE = {
    "loan_read",
    "loan_application",
    "loan_repayment",
    "payment_intent",
    "wallet_read",
}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Process liveness, not financial system readiness."""
    return {"status": "ok"}


@app.get("/api/v1/capabilities")
async def capabilities() -> dict[str, object]:
    """Public non-sensitive feature capability response."""
    return {
        "mode": "integration_disabled",
        "capabilities": {name: False for name in sorted(_UNAVAILABLE)},
    }


@app.get("/api/v1/me/loans", include_in_schema=False)
@app.post("/api/v1/loans/applications", include_in_schema=False)
@app.post("/api/v1/payments/intents", include_in_schema=False)
@app.get("/api/v1/me/wallet", include_in_schema=False)
async def financial_routes_disabled() -> JSONResponse:
    # 503 rather than fake approval, data or balance; no upstream call happens.
    return JSONResponse(
        status_code=503,
        content={
            "code": "INTEGRATION_DISABLED",
            "message": "Financial services are not available in this environment.",
        },
        headers={"Cache-Control": "no-store"},
    )
