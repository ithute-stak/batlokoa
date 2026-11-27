"""Service directory contract tests; synthetic credentials and identities."""
import httpx
import pytest
from uuid import uuid4

from backend.app.staff_morning_loanhub_directory import LoanHubMorningDirectory

COMPANY = uuid4()
EMPLOYEE = uuid4()
TOKEN = "synthetic-service-token"


def payload():
    return {"company_id": str(COMPANY), "complete": True, "employees": [
        {"company_id": str(COMPANY), "employee_id": str(EMPLOYEE),
         "role": "LOAN_OFFICER", "active": True}]}


def directory(handler, client):
    return LoanHubMorningDirectory(origin="https://loanhub.example",
        company_id=COMPANY, token=TOKEN, client=client)


def test_verified_directory_contract():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/integrations/attendance/employees"
        assert request.url.params["company_id"] == str(COMPANY)
        assert request.url.params["limit"] == "100"
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        assert "cookie" not in request.headers
        return httpx.Response(200, json=payload())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = directory(handler, client).employees(company_id=COMPANY, limit=100)
    assert len(rows) == 1
    assert rows[0].user_id == EMPLOYEE
    assert rows[0].company_id == COMPANY
    assert rows[0].active is True
    assert rows[0].company_wide_scope is False


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(complete=False),
    lambda p: p.update(company_id=str(uuid4())),
    lambda p: p["employees"][0].update(company_id=str(uuid4())),
    lambda p: p["employees"][0].update(active=1),
    lambda p: p["employees"][0].update(employee_id="invalid"),
    lambda p: p["employees"].append(p["employees"][0].copy()),
    lambda p: p.update(employees=None),
])
def test_invalid_membership_responses_fail_closed(mutate):
    data = payload()
    mutate(data)
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=data))) as client:
        with pytest.raises(ValueError, match="unavailable"):
            directory(None, client).employees(company_id=COMPANY, limit=100)


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 429, 503])
def test_no_redirect_or_unauthorized_directory(status):
    calls = []
    def handler(request):
        calls.append(request.url)
        return httpx.Response(status, headers={"Location": "https://other.example/"})
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(ValueError):
            directory(handler, client).employees(company_id=COMPANY, limit=100)
    assert len(calls) == 1


def test_scope_mismatch_never_contacts_upstream():
    def handler(request):
        pytest.fail("Unexpected upstream call")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            directory(handler, client).employees(company_id=uuid4(), limit=100)


def test_oversized_response_rejected():
    with httpx.Client(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, content=b"x" * 131073,
                headers={"Content-Type": "application/json"}))) as client:
        with pytest.raises(ValueError):
            directory(None, client).employees(company_id=COMPANY, limit=100)
