import time
from fastapi.testclient import TestClient
from app import coach, store, practice
from app.main import app


def submission(id, t, verdict, index="A"):
    return {
        "id": id,
        "creationTimeSeconds": t,
        "verdict": verdict,
        "problem": {
            "contestId": 1,
            "index": index,
            "name": "Example",
            "rating": 1000,
            "tags": ["dp"],
            "type": "PROGRAMMING",
        },
    }


def test_novice_roles_reject_1700_warmup_and_2100_main():
    analysis = coach.analyze([submission(1, 0, "OK")], 1)
    rows = []
    for i, rating in enumerate([900, 1000, 1100, 1200, 1700, 2100]):
        rows.append({**submission(i + 2, 0, "OK", str(i))["problem"], "rating": rating})

    class Overconfident:
        def predict_proba(self, rows):
            return [[0.4, 0.6] for _ in rows]

    result = coach.recommend(rows, analysis, model=Overconfident(), rating=1048)
    ceilings = {"Warm-up": 1000, "Main challenge": 1100, "Stretch": 1200}
    assert result and all(p["rating"] <= ceilings[p["role"]] for p in result)
    only_main = coach.recommend([rows[2]], analysis, model=Overconfident(), rating=1048)
    assert only_main[0]["role"] == "Main challenge"


def test_browse_filters_pagination_and_solve_status():
    rows = [submission(i, 0, "OK", str(i))["problem"] for i in range(5)]
    rows.append({**rows[0], "index": "unrated", "rating": None, "tags": ["geometry"]})
    a = {"solved": ["1:0"], "attempted": ["1:0", "1:1"], "topics": []}
    assert practice.browse(rows, a, page_size=2)["pages"] == 3
    assert practice.browse(rows, a, state="attempted")["items"][0]["key"] == "1:1"
    assert (
        practice.browse(rows, a, category_id="dp", include_unrated=False)["total"] == 5
    )
    assert practice.browse(rows, a, category_id="geometry")["total"] == 1
    assert practice.browse(rows, a, search="Example", state="unattempted")["total"] == 4


def test_failed_catalog_refresh_preserves_previous_data(tmp_path, monkeypatch):
    from app.main import cf

    monkeypatch.setenv("UPSOLVE_DB", str(tmp_path / "catalog.sqlite3"))

    async def fail(*args, **kwargs):
        raise ValueError("Upstream failure")

    monkeypatch.setattr(cf, "call", fail)
    with store.connect() as db:
        store.put(
            db, "catalog", "public", {"problems": [submission(1, 0, "OK")["problem"]]}
        )
    with TestClient(app) as client:
        assert client.post("/api/v1/problems/refresh").status_code == 502
        assert client.get("/api/v1/problems").json()["total"] == 1


def test_routes_and_experimental_classifier_is_not_ability_model(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSOLVE_DB", str(tmp_path / "test.sqlite3"))
    rows = [
        {**submission(i, 0, "OK", str(i))["problem"], "rating": rating}
        for i, rating in enumerate([900, 1000, 1100, 1700, 2100])
    ]
    with store.connect() as db:
        store.put(db, "catalog", "public", {"updated": time.time(), "problems": rows})
        store.put(
            db,
            "profile",
            "alice",
            {
                "handle": "alice",
                "rating": 1048,
                "maxRating": 1162,
                "sample": False,
                "submissions": [],
                "updated": time.time(),
            },
        )
        store.put(
            db,
            "model",
            "active",
            {"intercept": 99, "coefficients": [0, 0, 0], "metrics": {}},
        )
    with TestClient(app) as client:
        assert client.get("/problemset").status_code == 200
        assert client.get("/gym").status_code == 200
        assert client.get("/api/v1/problems?page_size=2").json()["total"] == 5
        assert (
            client.get("/api/v1/problems?minimum=2000&maximum=1000").status_code == 422
        )
        assert client.get("/api/v1/problems?state=solved").status_code == 422
        assert client.get("/api/v1/problems?category=invalid").status_code == 422
        dashboard = client.get("/api/v1/profiles/alice/dashboard").json()
        assert dashboard["model"] == "Topic Elo heuristic"
        assert all(p["rating"] <= 1200 for p in dashboard["recommendations"])
        gym = client.get("/api/v1/profiles/alice/gym").json()
        assert len(gym["topics"]) == len(practice.TOPICS)
        assert all(
            p["rating"] <= 1200
            for topic in gym["topics"]
            for p in topic["recommendations"]
        )
