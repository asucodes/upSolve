"""Resumable large IIT Kanpur imports. Run while the web server is stopped."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from app import coach, ml, store
from app.codeforces import Codeforces
from scripts.train_iitk import SOURCE_PAGE, select_cohort


def write_manifest(manifest):
    path = Path("data/large_training_manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(path)


async def import_profile(cf, user, prefix):
    handle = user["handle"]
    with store.connect() as db:
        old = store.get(db, "profile", handle)
        checkpoint = store.get(db, "import_checkpoint", handle, {})
    if (
        old
        and not old.get("sample")
        and time.time() - old.get("updated", 0) < 7 * 86400
    ):
        return old, True
    rows = {s["id"]: s for s in checkpoint.get("submissions", [])}
    offset = 1
    # Restart the page scan on resume: stable-ID early stopping would truncate
    # an unfinished historical import. Completed profiles are skipped above.
    while True:
        page = await cf.call(
            "user.status", handle=handle, **{"from": offset, "count": 1000}
        )
        for row in page:
            rows[row["id"]] = row
        with store.connect() as db:
            store.put(
                db,
                "import_checkpoint",
                handle,
                {"submissions": list(rows.values()), "updated": time.time()},
            )
        print(f"{prefix} {handle}: {len(rows)} submissions", flush=True)
        if len(page) < 1000:
            break
        offset += len(page)
    profile = {
        **user,
        "submissions": list(rows.values()),
        "contest_history": old.get("contest_history", []) if old else [],
        "sample": False,
        "updated": time.time(),
        "training_source": "IIT Kanpur exact organization text",
    }
    with store.connect() as db:
        store.put(db, "profile", handle, profile)
        db.execute(
            "DELETE FROM records WHERE kind=? AND id=?",
            ("import_checkpoint", handle.lower()),
        )
    return profile, False


async def run(limit, refresh_roster=False, train_only=False):
    cf = Codeforces()
    roster_path = Path("data/iitk_roster.json")
    if not refresh_roster and roster_path.exists():
        users = json.loads(roster_path.read_text(encoding="utf-8"))
    else:
        users = await cf.call(
            "user.ratedList", activeOnly="false", includeRetired="true"
        )
        users = [
            u
            for u in users
            if u.get("organization", "").strip().casefold() == "iit kanpur"
        ]
        roster_path.parent.mkdir(parents=True, exist_ok=True)
        roster_path.write_text(json.dumps(users), encoding="utf-8")
    selected = select_cohort(users, limit)
    if len(selected) < limit:
        raise RuntimeError(
            f"Requested {limit} profiles but only {len(selected)} exact matches exist."
        )
    manifest = {
        "requested_source": SOURCE_PAGE,
        "actual_source": "https://codeforces.com/api/user.ratedList?activeOnly=false&includeRetired=true",
        "organization_filter": "Exact IIT Kanpur text; numeric ID 470 is not exposed by this API",
        "roster_profiles": len(users),
        "selection": "Evenly spaced across sorted current ratings, including inactive and retired profiles",
        "target": limit,
        "started_at": time.time(),
        "status": "importing",
        "profiles": [],
    }
    write_manifest(manifest)
    if not train_only:
        with store.connect() as db:
            catalog = store.get(db, "catalog", "public", {})
        if time.time() - catalog.get("updated", 0) > 86400:
            result = await cf.call("problemset.problems")
            with store.connect() as db:
                store.put(
                    db,
                    "catalog",
                    "public",
                    {"updated": time.time(), "problems": result["problems"]},
                )
    for i, user in enumerate(selected, 1):
        try:
            if train_only:
                with store.connect() as db:
                    profile = store.get(db, "profile", user["handle"])
                if not profile or profile.get("sample"):
                    raise ValueError("No completed real import")
                cached = True
            else:
                profile, cached = await import_profile(cf, user, f"[{i}/{limit}]")
            item = {
                "handle": user["handle"],
                "status": "complete",
                "rating_at_selection": user.get("rating"),
                "submissions": len(profile["submissions"]),
                "imported_at": profile["updated"],
                "cached": cached,
            }
        except Exception as exc:
            item = {
                "handle": user["handle"],
                "status": "failed",
                "message": str(exc)[:400],
            }
        manifest["profiles"].append(item)
        write_manifest(manifest)
        print(
            f"[{i}/{limit}] {user['handle']}: {item['status']} ({item.get('submissions', 0)} submissions)",
            flush=True,
        )
    completed = [p for p in manifest["profiles"] if p["status"] == "complete"]
    if len(completed) < min(300, limit):
        manifest.update(status="incomplete", completed_at=time.time())
        write_manifest(manifest)
        raise RuntimeError(
            f"Only {len(completed)} completed imports. Previous active model preserved. Rerun to retry failures."
        )
    manifest["status"] = "training"
    write_manifest(manifest)
    examples = []
    profile_counts = []
    now = time.time()
    for item in completed:
        with store.connect() as db:
            profile = store.get(db, "profile", item["handle"])
        samples = coach.analyze(profile["submissions"], now)["examples"]
        examples.extend(samples)
        profile_counts.append(
            {"handle": item["handle"], "completed_attempts": len(samples)}
        )
    contributing = sum(p["completed_attempts"] > 0 for p in profile_counts)
    if contributing < min(300, limit):
        manifest.update(
            status="insufficient_contributing_profiles",
            contributing_profiles=contributing,
            profile_attempts=profile_counts,
        )
        write_manifest(manifest)
        raise RuntimeError(
            f"Only {contributing} profiles contribute rated attempts. Increase --limit. Previous model preserved."
        )
    print(
        f"Training on {len(examples)} completed attempts from {contributing} contributing profiles",
        flush=True,
    )
    artifact = ml.train(examples)
    manifest.update(
        status="complete",
        completed_at=time.time(),
        contributing_profiles=contributing,
        completed_attempts=len(examples),
        profile_attempts=profile_counts,
    )
    artifact.update(
        handles=[p["handle"] for p in profile_counts if p["completed_attempts"]],
        trained_at=time.time(),
        provenance=manifest,
    )
    report = {
        "profiles": contributing,
        "imported_profiles": len(completed),
        "submissions": sum(p["submissions"] for p in completed),
        "completed_attempts": len(examples),
        "metrics": artifact["metrics"],
        "completed_at": manifest["completed_at"],
    }
    # Replace the active artifact only once all imports, training, and evaluation succeed.
    with store.connect() as db:
        store.put(db, "model", "active", artifact)
    Path("data/large_training_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    write_manifest(manifest)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=320)
    parser.add_argument("--refresh-roster", action="store_true")
    parser.add_argument("--train-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 2000:
        parser.error("--limit must be between 1 and 2000")
    asyncio.run(run(args.limit, args.refresh_roster, args.train_only))
