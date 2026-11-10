import asyncio

import pytest

from app import ml, store
from scripts.train_cohort import import_profile


def test_partial_history_is_resumed_without_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSOLVE_DB", str(tmp_path / "training.sqlite3"))
    user = {"handle": "alice", "organization": "IIT Kanpur"}

    class Transport:
        failing = True

        async def call(self, method, **params):
            if params["from"] == 1:
                return [{"id": i} for i in range(1000)]
            if self.failing:
                raise RuntimeError("Interrupted connection")
            return [{"id": 1000}]

    transport = Transport()
    with pytest.raises(RuntimeError):
        asyncio.run(import_profile(transport, user, "[1/1]"))
    with store.connect() as db:
        assert store.get(db, "profile", "alice") is None
        assert len(store.get(db, "import_checkpoint", "alice")["submissions"]) == 1000
    transport.failing = False
    profile, cached = asyncio.run(import_profile(transport, user, "[1/1]"))
    assert not cached and len(profile["submissions"]) == 1001
    with store.connect() as db:
        assert store.get(db, "import_checkpoint", "alice") is None
    _, cached = asyncio.run(import_profile(transport, user, "[1/1]"))
    assert cached


def test_final_holdout_does_not_select_hyperparameters_or_coefficients():
    examples = [
        {
            "start": i * 100000,
            "end": i * 100000 + 100,
            "outcome": i % 2,
            "features": [(-1) ** i, 1, 1],
            "probability": 0.5,
        }
        for i in range(100)
    ]
    original = ml.train(examples)
    changed = ml.train(
        [
            {**e, "outcome": 1 - e["outcome"]} if i >= 80 else e
            for i, e in enumerate(examples)
        ]
    )
    assert original["coefficients"] == changed["coefficients"]
    assert original["metrics"]["selected_C"] == changed["metrics"]["selected_C"]
    assert original["metrics"]["brier"] < changed["metrics"]["brier"]
