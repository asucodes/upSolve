import random
import time


def fixture():
    rng = random.Random(42)
    topics = ["implementation", "greedy", "math", "binary search", "dp", "graphs"]
    now = int(time.time())
    catalog, submissions = [], []
    for i in range(240):
        topic = topics[i % len(topics)]
        p = {
            "contestId": 900000 + i,
            "index": "A",
            "name": f"{topic.title()} exercise {i + 1}",
            "type": "PROGRAMMING",
            "rating": 800 + (i % 7) * 100,
            "tags": [topic],
        }
        catalog.append(p)
        if i < 110:
            t = now - (120 - i) * 86400 + rng.randrange(3600)
            submissions.append(
                {
                    "id": i * 2,
                    "creationTimeSeconds": t,
                    "problem": p,
                    "verdict": "WRONG_ANSWER",
                }
            )
            if rng.random() < (0.8 if topic in ["implementation", "math"] else 0.5):
                submissions.append(
                    {
                        "id": i * 2 + 1,
                        "creationTimeSeconds": t + 3600,
                        "problem": p,
                        "verdict": "OK",
                    }
                )
    return {"handle": "demo", "rating": 1120, "sample": True}, catalog, submissions
