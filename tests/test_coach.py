from app.coach import analyze, recommend, WINDOW
from app.ml import train, Predictor
import pytest


def submission(id, t, verdict, index="A", tags=None):
    return {
        "id": id,
        "creationTimeSeconds": t,
        "verdict": verdict,
        "problem": {
            "contestId": 1,
            "index": index,
            "name": "Example",
            "rating": 1000,
            "tags": tags or ["dp"],
            "type": "PROGRAMMING",
        },
    }


def test_retries_are_one_success_and_repeated_solves_ignored():
    rows = [
        submission(1, 0, "WRONG_ANSWER"),
        submission(2, 100, "WRONG_ANSWER"),
        submission(3, 200, "OK"),
        submission(4, 400, "OK"),
    ]
    a = analyze(rows, WINDOW * 2)
    assert len(a["examples"]) == 1
    assert a["topics"][0]["rating"] == 1016
    assert a["topics"][0]["evidence"] == 1


def test_open_attempt_pending_judgments_and_compilation_errors_are_not_failures():
    assert not analyze([submission(1, 0, "COMPILATION_ERROR")], WINDOW * 2)["examples"]
    assert not analyze([submission(1, 0, "TESTING")], WINDOW * 2)["examples"]
    assert not analyze([submission(1, 0, "WRONG_ANSWER")], WINDOW - 1)["examples"]
    assert (
        analyze([submission(1, 0, "WRONG_ANSWER")], WINDOW)["examples"][0]["outcome"]
        == 0
    )


def test_time_order_replay_does_not_leak_future_outcomes():
    rows = [
        submission(1, 0, "WRONG_ANSWER"),
        submission(2, 100, "OK", "B"),
        submission(3, 200, "OK"),
    ]
    a = analyze(rows, WINDOW * 2)
    assert a["examples"][0]["features"][0] == 0
    assert a["examples"][1]["features"][0] == 0
    assert analyze(rows[::-1], WINDOW * 2) == a


def test_multitag_updates_split_credit():
    a = analyze([submission(1, 0, "OK", tags=["dp", "math"])], 1)
    assert [t["rating"] for t in a["topics"]] == [1008, 1008]


def test_solved_total_includes_unrated_problems_but_deduplicates_repeat_accepts():
    unrated = submission(1, 0, "OK")
    unrated["problem"].pop("rating")
    analysis = analyze(
        [unrated, submission(2, 1, "OK"), submission(3, 2, "OK", "B")], 3
    )
    assert len(analysis["solved"]) == 2


def test_recommendations_exclude_attempted_and_keep_probability_band():
    a = analyze([submission(1, 0, "OK")], 1)
    catalog = [submission(2, 0, "OK", x)["problem"] for x in ["A", "B", "C", "D"]]
    r = recommend(catalog, a)
    assert len(r) == 3
    assert all(p["index"] != "A" and 0.5 <= p["probability"] <= 0.7 for p in r)
    assert len({p["key"] for p in r}) == 3


def test_model_refuses_small_dataset_and_evaluates_future():
    with pytest.raises(ValueError):
        train([])
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
    artifact = train(examples)
    assert artifact["metrics"]["training_attempts"] == 80
    assert artifact["metrics"]["test_attempts"] == 20
    assert artifact["metrics"]["brier"] < artifact["metrics"]["elo_brier"]
    assert Predictor(artifact).predict_proba([[1, 1, 1]])[0][1] < 0.5
