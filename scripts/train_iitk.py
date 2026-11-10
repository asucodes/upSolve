"""Import a reproducible IIT Kanpur cohort and train the shared classifier.

Run with the web server stopped: uv run python -m scripts.train_iitk --limit 8
The linked organization page may block automated access. The supported public
API supplies organization text, not numeric organization IDs; record that
distinction rather than claiming the page itself was scraped.
"""

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path

from app.main import cf, sync
from app import store, coach, ml

SOURCE_PAGE = "https://codeforces.com/ratings/organization/470/page/1"


def select_cohort(users, limit):
    candidates = sorted(
        [
            u
            for u in users
            if u.get("organization", "").strip().casefold() == "iit kanpur"
        ],
        key=lambda u: (u.get("rating", 0), u["handle"].casefold()),
    )
    if len(candidates) <= limit:
        return candidates
    if limit == 1:
        return [candidates[len(candidates) // 2]]
    return [
        candidates[round(i * (len(candidates) - 1) / (limit - 1))] for i in range(limit)
    ]


async def run(limit):
    print(
        "Discovering active rated IIT Kanpur profiles through the public API",
        flush=True,
    )
    users = await cf.call("user.ratedList", activeOnly="true", includeRetired="false")
    selected = select_cohort(users, limit)
    if not selected:
        raise RuntimeError(
            "No exact IIT Kanpur organization matches. No dataset was changed."
        )
    manifest = {
        "requested_source": SOURCE_PAGE,
        "actual_source": "https://codeforces.com/api/user.ratedList?activeOnly=true&includeRetired=false",
        "organization_filter": "IIT Kanpur (exact text, not verified numeric organization ID)",
        "selection": "Evenly spaced across sorted current ratings of active public profiles",
        "started_at": time.time(),
        "profiles": [],
    }
    for user in selected:
        print(f"Importing {user['handle']} (rating {user.get('rating')})", flush=True)
        job = {
            "id": uuid.uuid4().hex,
            "handle": user["handle"],
            "status": "queued",
            "message": "",
        }
        await sync(job)
        manifest["profiles"].append(
            {
                "handle": user["handle"],
                "rating_at_selection": user.get("rating"),
                "organization": user.get("organization"),
                "status": job["status"],
                "message": job["message"],
                "imported_at": time.time(),
            }
        )
        print(job["status"] + ": " + job["message"], flush=True)
        Path("data").mkdir(exist_ok=True)
        Path("data/training_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    completed = {
        p["handle"].casefold()
        for p in manifest["profiles"]
        if p["status"] == "complete"
    }
    with store.connect() as db:
        profiles = [
            p
            for p in store.all_records(db, "profile")
            if not p["sample"] and p["handle"].casefold() in completed
        ]
    examples = [
        e
        for p in profiles
        for e in coach.analyze(p["submissions"], time.time())["examples"]
    ]
    artifact = ml.train(examples)
    artifact.update(
        handles=sorted(p["handle"] for p in profiles),
        trained_at=time.time(),
        provenance=manifest,
    )
    with store.connect() as db:
        store.put(db, "model", "active", artifact)
    print(
        json.dumps(
            {"handles": artifact["handles"], "metrics": artifact["metrics"]}, indent=2
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=8, choices=range(1, 31), metavar="1..30"
    )
    asyncio.run(run(parser.parse_args().limit))
