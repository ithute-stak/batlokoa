"""Read-only LoanHub employer dropdown parser guardrails."""
from uuid import uuid4

import pytest

from backend.app.staff_registration_employer_routes import _validated_employers


def row(**changes):
    item = dict(
        id=str(uuid4()), code="LMPS",
        name="Lesotho Mounted Police Service", is_active=True,
    )
    item.update(changes)
    return item


def test_valid_employer_groups_preserve_loanhub_ids_and_names():
    original = row()
    assert _validated_employers([original]) == [{
        "id": original["id"], "code": "LMPS",
        "name": "Lesotho Mounted Police Service",
    }]


@pytest.mark.parametrize("invalid", [
    {"is_active": False},
    {"id": "not-a-uuid"},
    {"name": ""},
    {"code": ""},
    {"name": "x" * 201},
])
def test_invalid_employer_rows_fail_closed(invalid):
    with pytest.raises((ValueError, KeyError, TypeError)):
        _validated_employers([row(**invalid)])


def test_duplicate_employer_id_rejected():
    original = row()
    with pytest.raises(ValueError):
        _validated_employers([original, original])


def test_invalid_collection_and_oversized_directory_rejected():
    with pytest.raises(ValueError):
        _validated_employers({"employers": []})
    with pytest.raises(ValueError):
        _validated_employers([row() for _ in range(501)])
