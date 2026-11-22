"""Restricted employee pilot activation tests: no live LoanHub requests."""
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.employee_pilot_bootstrap import (
    ACK, KEY_PATH, LOANHUB_ORIGIN, MODE, PUBLIC_ORIGIN,
    configure_employee_pilot,
)
from backend.app.loanhub_staff_verifier import LoanHubStaffVerifier
from backend.app.staff_login_routes import StaffLoginConfig


def configure(monkeypatch, tmp_path, *, directory=False):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_file = tmp_path / "verification.pem"
    key_file.write_bytes(pem)
    actual_lstat = Path.lstat
    actual_read = Path.read_bytes

    def scoped_lstat(self):
        return actual_lstat(key_file if str(self) == KEY_PATH else self)

    def scoped_read(self):
        return actual_read(key_file if str(self) == KEY_PATH else self)

    monkeypatch.setattr(Path, "lstat", scoped_lstat)
    monkeypatch.setattr(Path, "read_bytes", scoped_read)
    company = str(uuid4())
    for name, value in {
        "BATLOKOA_EMPLOYEE_PILOT_MODE": MODE,
        "BATLOKOA_EMPLOYEE_PILOT_ACK": ACK,
        "BATLOKOA_EMPLOYEE_PUBLIC_ORIGIN": PUBLIC_ORIGIN,
        "BATLOKOA_EMPLOYEE_LOANHUB_ORIGIN": LOANHUB_ORIGIN,
        "BATLOKOA_EMPLOYEE_COMPANY_ID": company,
        "BATLOKOA_EMPLOYEE_READONLY_DIRECTORY": "true" if directory else "false",
    }.items():
        monkeypatch.setenv(name, value)
    return company


def test_pilot_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BATLOKOA_EMPLOYEE_PILOT_MODE", raising=False)
    app = FastAPI()
    assert configure_employee_pilot(app) is False
    assert not hasattr(app.state, "staff_login_config")


def test_invalid_pilot_approval_never_attaches_config(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("BATLOKOA_EMPLOYEE_PILOT_ACK", "UNAPPROVED")
    app = FastAPI()
    with pytest.raises(ValueError):
        configure_employee_pilot(app)
    assert not hasattr(app.state, "staff_login_config")


def test_wrong_loan_hub_origin_is_rejected(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("BATLOKOA_EMPLOYEE_LOANHUB_ORIGIN", "https://attacker.example")
    app = FastAPI()
    with pytest.raises(ValueError):
        configure_employee_pilot(app)
    assert not hasattr(app.state, "staff_login_config")


def test_trusted_pilot_wires_verified_login_only(monkeypatch, tmp_path):
    company = configure(monkeypatch, tmp_path)
    app = FastAPI()
    assert configure_employee_pilot(app) is True
    config = app.state.staff_login_config
    assert isinstance(config, StaffLoginConfig)
    assert isinstance(config.verifier, LoanHubStaffVerifier)
    assert str(config.verifier._company_id) == company
    assert config.public_origin == PUBLIC_ORIGIN
    assert config.loanhub_origin == LOANHUB_ORIGIN
    assert not hasattr(app.state, "staff_client_directory_enabled")


def test_directory_requires_additional_explicit_opt_in(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, directory=True)
    app = FastAPI()
    assert configure_employee_pilot(app) is True
    assert app.state.staff_client_directory_enabled is True
    assert app.state.staff_client_directory._origin == LOANHUB_ORIGIN


def test_invalid_key_is_rejected_before_login_routes_are_attached(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    # Invalid PEM must cause bootstrap to fail; never permit a fallback key.
    real_read = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"x" * 200)
    app = FastAPI()
    with pytest.raises((ValueError, TypeError)):
        configure_employee_pilot(app)
    assert not hasattr(app.state, "staff_login_config")
