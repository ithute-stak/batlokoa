"""The staged Save Client BFF endpoint must never expose live writes."""
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.staff_client_creation_routes import (
    register_client, router,
)

PATH = "/api/v1/staff/clients/register"


def test_staged_write_route_is_not_mounted_on_live_app():
    assert any(getattr(route, "path", "") == PATH for route in router.routes)
    assert not any(getattr(route, "path", "") == PATH for route in app.routes)


def test_staged_write_handler_unconfigured_fails_closed():
    import asyncio
    from unittest.mock import Mock
    from backend.app import staff_client_creation_routes as routes
    from fastapi import Request
    request = Mock()
    request.app.state.staff_login_config = None
    response = asyncio.run(register_client(request))
    assert response.status_code == 503
    assert b"REGISTRATION_UNAVAILABLE" in response.body


def test_release_gate_is_fixed_false():
    from backend.app.staff_client_creation_routes import _release_approved
    assert _release_approved() is False
