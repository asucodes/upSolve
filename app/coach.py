"""Deterministic, event-time coaching. No feature may see a later outcome."""

from collections import defaultdict
from math import log1p

FAILURES = {
    "WRONG_ANSWER",
    "RUNTIME_ERROR",
    "TIME_LIMIT_EXCEEDED",
    "MEMORY_LIMIT_EXCEEDED",
    "IDLENESS_LIMIT_EXCEEDED",
    "CHALLENGED",
}
WINDOW = 86400


def key(problem):
    return f"{problem.get('contestId', '')}:{problem['index']}"


def probability(skill, difficulty):
    return 1 / (1 + 10 ** (max(-4000, min(4000, difficulty - skill)) / 400))


def analyze(submissions, now):
    grouped = defaultdict(list)
    solved, attempted = set(), set()
    activity = []
    for s in sorted(submissions, key=lambda s: (s["creationTimeSeconds"], s["id"])):
        if s["creationTimeSeconds"] > now:
            continue
        p = s["problem"]
        k = key(p)
        attempted.add(k)
        if s.get("verdict") == "OK":
            solved.add(k)
        activity.append(
            {
                "time": s["creationTimeSeconds"],
                "accepted": s.get("verdict") == "OK",
                "problem": k,
            }
        )
        if p.get("rating") and p.get("tags") and s.get("verdict") in FAILURES | {"OK"}:
            grouped[k].append(s)
    episodes = []
    for k, rows in grouped.items():
        current = None
        for s in rows:
            t = s["creationTimeSeconds"]
            if current and t >= current["start"] + WINDOW:
                episodes.append(current)
                current = None
            if current is None:
                current = {
                    "start": t,
                    "end": t + WINDOW,
                    "outcome": 0,
                    "problem": s["problem"],
                    "key": k,
                }
            if s["verdict"] == "OK":
                current.update(end=t, outcome=1)
                episodes.append(current)
                current = None
                break
        if current:
            episodes.append(current)
    ratings = defaultdict(lambda: 1000.0)
    evidence = defaultdict(set)
    history, examples = [], []
    events = []
    for i, ep in enumerate(episodes):
        # Features first when acceptance occurs at the start of the same attempt.
        events.extend([(ep["start"], 1, i, "start"), (ep["end"], 2, i, "end")])
    prepared = {}
    for t, _, i, kind in sorted(events):
        if t > now:
            continue
        ep = episodes[i]
        tags = ep["problem"]["tags"]
        if kind == "start":
            skill = sum(ratings[tag] for tag in tags) / len(tags)
            count = max((len(evidence[tag]) for tag in tags), default=0)
            prepared[i] = {
                "features": [
                    (skill - ep["problem"]["rating"]) / 400,
                    log1p(count),
                    len(tags),
                ],
                "probability": probability(skill, ep["problem"]["rating"]),
            }
        else:
            sample = prepared[i]
            examples.append(
                {
                    **sample,
                    "start": ep["start"],
                    "end": ep["end"],
                    "outcome": ep["outcome"],
                }
            )
            change = 32 * (ep["outcome"] - sample["probability"]) / len(tags)
            for tag in tags:
                ratings[tag] += change
                evidence[tag].add(ep["key"])
                history.append(
                    {"time": t, "topic": tag, "rating": round(ratings[tag], 1)}
                )
    return {
        "topics": [
            {
                "name": t,
                "rating": round(ratings[t], 1),
                "evidence": len(evidence[t]),
                "provisional": len(evidence[t]) < 5,
            }
            for t in sorted(ratings)
        ],
        "history": history,
        "examples": examples,
        "solved": sorted(solved),
        "attempted": sorted(attempted),
        "activity": activity,
    }


def recommend(catalog, analysis, focus=(), model=None, limit=3):
    topics = {t["name"]: t for t in analysis["topics"]}
    candidates = []
    for p in catalog:
        tags = p.get("tags", [])
        if (
            not p.get("rating")
            or not tags
            or not p.get("contestId")
            or p.get("type", "PROGRAMMING") != "PROGRAMMING"
            or key(p) in analysis["attempted"]
        ):
            continue
        skill = sum(topics.get(t, {}).get("rating", 1000) for t in tags) / len(tags)
        count = max((topics.get(t, {}).get("evidence", 0) for t in tags), default=0)
        estimate = (
            probability(skill, p["rating"])
            if model is None
            else float(
                model.predict_proba(
                    [[(skill - p["rating"]) / 400, log1p(count), len(tags)]]
                )[0][1]
            )
        )
        if 0.5 <= estimate <= 0.7:
            matched = sorted(set(tags) & set(focus))
            candidates.append(
                {
                    **p,
                    "key": key(p),
                    "probability": round(estimate, 4),
                    "model": "logistic regression"
                    if model is not None
                    else "Elo fallback",
                    "reason": f"Focus: {', '.join(matched)}. "
                    if matched
                    else "Matches your current topic estimates. ",
                    "focused": bool(matched),
                    "url": f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}",
                }
            )
    chosen = []
    for target in [0.7, 0.6, 0.5][:limit]:
        if not candidates:
            break
        candidates.sort(
            key=lambda p: (not p["focused"], abs(p["probability"] - target), p["key"])
        )
        chosen.append(candidates.pop(0))
    return chosen
