"""For authenticated read-only GETs, browsers usually omit Origin.

Block explicit foreign origins and cross-site Fetch Metadata. Staff cookie and
LoanHub verification remain mandatory; no CORS credentials are granted.
"""
from fastapi import Request


def safe_staff_read_origin(request: Request, expected_origin: str) -> bool:
    origin = request.headers.get("origin")
    if origin is not None and origin != expected_origin.rstrip("/"):
        return False
    fetch_site = request.headers.get("sec-fetch-site", "")
    return fetch_site in ("", "same-origin", "none")
