import asyncio
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.codeforces import Codeforces
from app import store


def test_demo_plan_persistence_and_model_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSOLVE_DB", str(tmp_path / "test.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/v1/profiles/unknown/dashboard").status_code == 404
        assert client.post("/api/v1/demo").status_code == 200
        data = client.get("/api/v1/profiles/demo/dashboard").json()
        assert data["sample"] and data["model"] == "Topic Elo heuristic"
        assert data["analysis"]["solved"]
        assert data["recommendations"]
        assert (
            client.put(
                "/api/v1/profiles/demo/plan", json={"topics": ["dp"], "target": 7}
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/v1/profiles/demo/plan", json={"topics": ["invalid"], "target": 7}
            ).status_code
            == 422
        )
        assert client.post("/api/v1/model/train").status_code == 422
        assert (
            client.post("/api/v1/sync", json={"handle": "../oops"}).status_code == 422
        )
        assert client.get("/openapi.json").status_code == 200
    with TestClient(app) as client:
        assert (
            client.get("/api/v1/profiles/demo/dashboard").json()["plan"]["target"] == 7
        )


def test_failed_import_preserves_cached_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSOLVE_DB", str(tmp_path / "test.sqlite3"))
    from app.main import sync, cf

    async def fail(*args, **kwargs):
        raise ValueError("Upstream unavailable")

    monkeypatch.setattr(cf, "call", fail)
    with store.connect() as db:
        store.put(db, "profile", "alice", {"handle": "alice", "submissions": []})
    asyncio.run(
        sync({"id": "job1", "handle": "alice", "status": "queued", "message": ""})
    )
    with store.connect() as db:
        assert store.get(db, "profile", "alice")["handle"] == "alice"
        assert store.get(db, "job", "job1")["status"] == "failed"


def test_pagination_deduplication_and_pending_refresh():
    calls = []

    def handler(request):
        offset = int(request.url.params.get("from", "1"))
        calls.append(offset)
        rows = (
            [{"id": i, "verdict": "OK"} for i in range(2000, 1000, -1)]
            if offset == 1
            else [{"id": 1000, "verdict": "OK"}]
        )
        return httpx.Response(200, json={"status": "OK", "result": rows})

    cf = Codeforces(interval=0, transport=httpx.MockTransport(handler))
    rows = asyncio.run(
        cf.submissions("alice", [{"id": 1000, "verdict": "TESTING"}], lambda _: None)
    )
    assert calls == [1, 1001]
    assert len(rows) == 1001
    assert next(s for s in rows if s["id"] == 1000)["verdict"] == "OK"
