"""Unit tests for the shared backend-error sanitizer (#234 item 1).

Guards the contract every service's handlers now delegate to: a backend being
unreachable → 503 (retryable), any other failure → generic 500, and in NEITHER
case does the raw exception string leak into the response detail.
"""

import pytest

from shared.errors import backend_http_error, is_connectivity_error


# Names mirror the real driver exceptions we classify by module+class name+message
# (we don't import the drivers into `shared`, so stand-ins reproduce that surface).
class ServiceUnavailable(Exception):
    """neo4j.exceptions.ServiceUnavailable stand-in."""


class ConnectError(Exception):
    """httpx.ConnectError stand-in."""


@pytest.mark.parametrize(
    "exc",
    [
        ServiceUnavailable("Failed to establish connection to 10.0.0.5:7687"),
        ConnectError("All connection attempts failed"),
        ConnectionRefusedError("[Errno 111] Connection refused"),
        OSError("Temporary failure in name resolution"),
        TimeoutError("Connection timed out"),
    ],
)
def test_connectivity_errors_are_503(exc):
    err = backend_http_error(exc, "Knowledge graph construction")
    assert err.status_code == 503
    assert "unreachable" in err.detail.lower()


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("invalid tier 'XYZ'"),
        KeyError("entities"),
        RuntimeError("spaCy model not loaded"),
    ],
)
def test_non_connectivity_errors_are_500(exc):
    err = backend_http_error(exc, "Tool execution")
    assert err.status_code == 500


def test_operation_label_is_in_detail_but_raw_exception_is_not():
    secret = "postgresql://user:sup3rsecret@db:5432/minder"
    err = backend_http_error(RuntimeError(secret), "License validation")
    assert "License validation" in err.detail
    assert secret not in err.detail  # no raw str(e) leak
    assert "sup3rsecret" not in err.detail


def test_is_connectivity_error_predicate():
    assert is_connectivity_error(ServiceUnavailable("cannot connect"))
    assert not is_connectivity_error(ValueError("bad input"))
