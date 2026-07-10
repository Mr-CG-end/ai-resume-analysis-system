import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_reports_configured_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.delenv("REDIS_URL", raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "dependencies": {"ai": "configured", "redis": "disabled"},
    }
