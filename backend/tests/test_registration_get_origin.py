"""Regression: normal same-origin GETs omit Origin, unlike POST."""
from types import SimpleNamespace
import pytest

from backend.app.staff_registration_read_origin import safe_staff_read_origin


def request(**headers):
    return SimpleNamespace(headers=headers)


@pytest.mark.parametrize("headers,expected", [
    ({}, True),
    ({"sec-fetch-site": "same-origin"}, True),
    ({"sec-fetch-site": "none"}, True),
    ({"origin": "https://batlokoa.co.ls"}, True),
    ({"origin": "https://another.example"}, False),
    ({"sec-fetch-site": "cross-site"}, False),
    ({"sec-fetch-site": "same-site"}, False),
    ({"origin": "https://batlokoa.co.ls", "sec-fetch-site": "cross-site"}, False),
])
def test_registration_read_origin(headers, expected):
    assert safe_staff_read_origin(
        request(**headers), "https://batlokoa.co.ls") is expected
