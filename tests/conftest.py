import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_request():
    return {
        "method": "POST",
        "path": "/api/login",
        "protocol": "HTTP/1.1",
        "request_body": "username=admin&password=test",
    }


@pytest.fixture
def malicious_request():
    return {
        "method": "GET",
        "path": "/search",
        "protocol": "HTTP/1.1",
        "request_body": "<script>alert('xss')</script>",
    }
