import os
import subprocess
import sys

import httpx
import pytest

from app.main import app


async def test_ready_requires_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://erp:bad@127.0.0.1:1/erp_test")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/live")).status_code == 200
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["code"] == "NOT_READY"


def test_empty_database_migrates():
    from sqlalchemy import make_url

    url = os.environ.get("TEST_DATABASE_URL", "")
    assert url, "TEST_DATABASE_URL must point to an explicitly named erp_*_test database"
    assert make_url(url).database.startswith("erp_") and make_url(url).database.endswith("_test")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("url", ["sqlite:///test.db", "postgresql+asyncpg://localhost/erp_demo", "postgresql+asyncpg://localhost/customer_test"])
def test_refuse_unsafe_test_database(url):
    from app.core.db import require_test_database

    with pytest.raises(ValueError):
        require_test_database(url)


async def test_unexpected_errors_are_sanitized_and_structured():
    from fastapi import FastAPI
    from app.core.errors import install_errors
    test_app=FastAPI();install_errors(test_app)
    @test_app.get('/boom')
    async def boom(): raise ValueError('private-test-data')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app,raise_app_exceptions=False),base_url='http://test') as c:
        for path,status in [('/missing',404),('/boom',500)]:
            response=await c.get(path)
            assert response.status_code==status
            assert response.json()['request_id'] and response.json()['code']
            assert 'private-test-data' not in response.text
