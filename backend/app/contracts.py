"""Internal API contracts. These do NOT assert LoanHub or IthutePay endpoint compatibility."""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class Capability(StrEnum):
    LOAN_READ = "loan_read"
    LOAN_APPLICATION = "loan_application"
    LOAN_REPAYMENT = "loan_repayment"
    PAYMENT_INTENT = "payment_intent"
    WALLET_READ = "wallet_read"


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(pattern=r"^LSL$")
    minor_units: int = Field(ge=0, le=100_000_000_000)


class LoanSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loan_id: str = Field(min_length=1, max_length=120)
    status: str = Field(min_length=1, max_length=40)
    outstanding: Money


class PaymentIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loan_id: str = Field(min_length=1, max_length=120)
    amount_minor_units: int = Field(gt=0, le=100_000_000)
    idempotency_key: str = Field(min_length=16, max_length=128)


class PaymentIntentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    status: str


class LoanHubAdapter(Protocol):
    async def list_customer_loans(
        self, *, tenant_id: str, customer_id: str
    ) -> list[LoanSummary]: ...


class IthutePayAdapter(Protocol):
    async def request_payment_intent(
        self, *, tenant_id: str, customer_id: str, request: PaymentIntentRequest
    ) -> PaymentIntentResponse: ...
