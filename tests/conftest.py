import pytest
from fastapi.testclient import TestClient

from scamserp.app import create_app
from scamserp.config import Settings
from scamserp.seed import seed_registry


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, mode="live", admin_token="test-admin-token", api_key="test-key", daily_cap=5, monthly_cap=10, rate_limit=1000, min_runs=2)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def db(client, app):
    return app.state.db


@pytest.fixture
def pipeline(client, app):
    return app.state.pipeline


@pytest.fixture
def risky_payload():
    return {"search_metadata": {"id": "fixture-search", "status": "Success"}, "organic_results": [{"position": 1, "title": "SBI support fixture", "link": "https://sbi-care.example/", "snippet": "Test-only contact 1800 000 0000"}, {"position": 2, "title": "SBI official", "link": "https://sbi.bank.in/", "snippet": "Call 1800 1234"}]}


ADMIN = {"Authorization": "Bearer test-admin-token"}
