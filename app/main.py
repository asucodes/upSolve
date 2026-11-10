import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from typing import Literal
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import store, coach, ml, practice
from .codeforces import Codeforces
from .demo import fixture

cf = Codeforces()
tasks = set()
sync_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app):
    with store.connect() as db:
        for job in store.all_records(db, "job"):
            if job["status"] in {"queued", "running"}:
                job.update(
                    status="failed", message="Application restarted. Please sync again."
                )
                store.put(db, "job", job["id"], job)
    yield
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(
    title="upSolve API",
    version="0.1.0",
    description="Local Codeforces practice coaching. Partner integrations use /api/v1. No authentication; bind to loopback only.",
    lifespan=lifespan,
)
origins = [
    x.strip()
    for x in os.environ.get("UPSOLVE_CORS_ORIGINS", "").split(",")
    if x.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)
static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static), name="static")


class SyncRequest(BaseModel):
    handle: str = Field(min_length=1, max_length=24, pattern=r"^[A-Za-z0-9_.-]+$")


class Plan(BaseModel):
    topics: list[str] = Field(default_factory=list, max_length=2)
    target: int = Field(default=5, ge=1, le=50)


class Job(BaseModel):
    id: str
    handle: str
    status: str
    message: str


@app.get("/", include_in_schema=False)
@app.get("/problemset", include_in_schema=False)
@app.get("/gym", include_in_schema=False)
def index():
    return FileResponse(static / "index.html")


def practice_context(handle):
    profile = read_profile(handle) if handle else None
    sample = bool(profile and profile.get("sample"))
    with store.connect() as db:
        catalog = store.get(
            db,
            "catalog",
            "demo" if sample else "public",
            {"problems": [], "updated": None},
        )
    analysis = (
        coach.analyze(profile["submissions"], time.time())
        if profile
        else {"solved": [], "attempted": [], "topics": []}
    )
    return profile, catalog, analysis, sample


@app.post("/api/v1/problems/refresh")
async def refresh_problemset() -> dict:
    try:
        result = await cf.call("problemset.problems")
    except Exception as exc:
        raise HTTPException(
            502, "Codeforces catalog refresh failed; cached problems are preserved."
        ) from exc
    counts = {
        coach.key(p): p["solvedCount"] for p in result.get("problemStatistics", [])
    }
    problems = [
        {**p, "solvedCount": counts.get(coach.key(p))} for p in result["problems"]
    ]
    updated = time.time()
    with store.connect() as db:
        store.put(db, "catalog", "public", {"updated": updated, "problems": problems})
    return {"problems": len(problems), "updated": updated}


@app.get("/api/v1/practice/topics")
def practice_topics() -> list[dict]:
    return practice.TOPICS


@app.get("/api/v1/problems")
def problemset(
    handle: str | None = None,
    search: str = Query(default="", max_length=120),
    tag: str = "",
    category: str = "",
    minimum: int = Query(default=800, ge=0, le=4000),
    maximum: int = Query(default=4000, ge=0, le=4000),
    state: Literal["all", "solved", "attempted", "unattempted"] = "all",
    sort: Literal["newest", "difficulty"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    include_unrated: bool = True,
) -> dict:
    if minimum > maximum:
        raise HTTPException(422, "Minimum rating must not exceed maximum rating.")
    if category and not practice.category(category):
        raise HTTPException(422, "Unknown topic group.")
    if state != "all" and not handle:
        raise HTTPException(422, "Select a profile to filter by solve status.")
    _, catalog, analysis, sample = practice_context(handle)
    return {
        **practice.browse(
            catalog["problems"],
            analysis,
            search=search,
            tag=tag,
            category_id=category,
            minimum=minimum,
            maximum=maximum,
            state=state,
            sort=sort,
            page=page,
            page_size=page_size,
            include_unrated=include_unrated,
            sample=sample,
        ),
        "sample": sample,
        "catalog_updated": catalog.get("updated"),
    }


@app.get("/api/v1/profiles/{handle}/gym")
def topic_gym(handle: str) -> dict:
    profile, catalog, analysis, sample = practice_context(handle)
    return {
        "handle": profile["handle"],
        "sample": sample,
        **practice.gym(catalog["problems"], analysis, profile.get("rating"), sample),
    }


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}


def read_profile(handle):
    with store.connect() as db:
        profile = store.get(db, "profile", handle)
    if not profile:
        raise HTTPException(404, "Sync this handle first, or open the sample profile.")
    return profile


def job_update(job, **changes):
    job.update(changes)
    with store.connect() as db:
        store.put(db, "job", job["id"], job)


async def sync(job):
    async with sync_lock:
        try:
            job_update(job, status="running", message="Loading public profile")
            handle = job["handle"]
            info = (await cf.call("user.info", handles=handle))[0]
            with store.connect() as db:
                old = store.get(db, "profile", handle, {})
                catalog = store.get(db, "catalog", "public", {})
            rows = await cf.submissions(
                info["handle"],
                old.get("submissions", []),
                lambda message: job_update(job, message=message),
            )
            history = await cf.call("user.rating", handle=info["handle"])
            if time.time() - catalog.get("updated", 0) > 86400:
                job_update(job, message="Refreshing problem catalog")
                result = await cf.call("problemset.problems")
                catalog = {"updated": time.time(), "problems": result["problems"]}
            profile = {
                **info,
                "submissions": rows,
                "contest_history": history,
                "sample": False,
                "updated": time.time(),
            }
            # A failed fetch never replaces a previously complete profile or catalog.
            with store.connect() as db:
                store.put(db, "profile", handle, profile)
                store.put(db, "catalog", "public", catalog)
            job_update(
                job, status="complete", message=f"Imported {len(rows)} submissions"
            )
        except Exception as exc:
            job_update(
                job,
                status="failed",
                message=str(exc)[:400] or "Import failed; please retry.",
            )


@app.post("/api/v1/sync", response_model=Job, status_code=202)
async def start_sync(body: SyncRequest):
    if body.handle.lower() == "demo":
        raise HTTPException(422, "The handle demo is reserved for the sample profile.")
    with store.connect() as db:
        active = [
            j
            for j in store.all_records(db, "job")
            if j["handle"].lower() == body.handle.lower()
            and j["status"] in {"queued", "running"}
        ]
    if active:
        return active[0]
    job = {
        "id": uuid.uuid4().hex,
        "handle": body.handle,
        "status": "queued",
        "message": "Waiting for import",
    }
    job_update(job)
    task = asyncio.create_task(sync(job))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return job


@app.get("/api/v1/sync/{job_id}", response_model=Job)
def sync_status(job_id: str):
    with store.connect() as db:
        job = store.get(db, "job", job_id)
    if not job:
        raise HTTPException(404, "Unknown sync job")
    return job


@app.post("/api/v1/demo")
def load_demo() -> dict:
    info, catalog, submissions = fixture()
    with store.connect() as db:
        store.put(
            db,
            "profile",
            "demo",
            {
                **info,
                "submissions": submissions,
                "updated": time.time(),
                "contest_history": [],
            },
        )
        store.put(db, "catalog", "demo", {"problems": catalog})
    return {"handle": "demo"}


@app.get("/api/v1/profiles")
def profiles() -> list[dict]:
    with store.connect() as db:
        return [
            {"handle": row[0], "sample": bool(row[1]), "updated": row[2]}
            for row in db.execute(
                "SELECT json_extract(body, '$.handle'), json_extract(body, '$.sample'), json_extract(body, '$.updated') FROM records WHERE kind='profile' ORDER BY id"
            )
        ]


@app.get("/api/v1/profiles/{handle}/dashboard")
def dashboard(handle: str) -> dict:
    p = read_profile(handle)
    analysis = coach.analyze(p["submissions"], time.time())
    with store.connect() as db:
        plan = store.get(db, "plan", handle, {"topics": [], "target": 5})
        catalog = store.get(
            db, "catalog", "demo" if p["sample"] else "public", {"problems": []}
        )
        artifact = None if p["sample"] else store.get(db, "model", "active")
    recommendations = coach.recommend(
        catalog["problems"],
        analysis,
        plan["topics"],
        ml.Predictor(artifact)
        if artifact and artifact.get("recommendation_ready", False)
        else None,
        rating=p.get("rating"),
    )
    return {
        "handle": p["handle"],
        "sample": p["sample"],
        "updated": p["updated"],
        "official_rating": p.get("rating"),
        "submission_coverage": {
            "source": "synthetic sample"
            if p["sample"]
            else "Codeforces public user.status API",
            "submissions": len(p["submissions"]),
            "accepted_submissions": sum(
                s.get("verdict") == "OK" for s in p["submissions"]
            ),
            "unique_solved": len(analysis["solved"]),
            "profile_url": None
            if p["sample"]
            else "https://codeforces.com/profile/" + p["handle"],
            "note": "Public API solves can differ from the total shown on the Codeforces profile. Submissions unavailable through this API cannot contribute to coaching estimates.",
        },
        "contest_history": p.get("contest_history", []),
        "analysis": {k: v for k, v in analysis.items() if k != "examples"},
        "recommendations": recommendations,
        "plan": plan,
        "model": "logistic regression"
        if artifact and artifact.get("recommendation_ready", False)
        else "Topic Elo heuristic",
        "recommendation_note": "No unseen problems fit both the rating limits and the 50–70% heuristic band. Browse the Problemset to explore manually."
        if not recommendations
        else "Uncalibrated topic Elo estimates, constrained by your current rating. The experimental classifier predicts acceptance among submitted attempts and is not used as independent solve ability.",
    }


@app.put("/api/v1/profiles/{handle}/plan", response_model=Plan)
def save_plan(handle: str, plan: Plan):
    p = read_profile(handle)
    with store.connect() as db:
        catalogs = store.get(
            db, "catalog", "demo" if p["sample"] else "public", {"problems": []}
        )
        valid = {t for problem in catalogs["problems"] for t in problem.get("tags", [])}
        if any(t not in valid for t in plan.topics) or len(set(plan.topics)) != len(
            plan.topics
        ):
            raise HTTPException(422, "Select up to two distinct catalog topics.")
        store.put(db, "plan", handle, plan.model_dump())
    return plan


@app.get("/api/v1/topics")
def topics() -> list[str]:
    with store.connect() as db:
        return sorted(
            {
                tag
                for catalog in store.all_records(db, "catalog")
                for p in catalog["problems"]
                for tag in p.get("tags", [])
            }
        )


@app.get("/api/v1/model")
def model_status() -> dict:
    with store.connect() as db:
        artifact = store.get(db, "model", "active")
    return {
        "available": bool(artifact),
        "metrics": artifact["metrics"] if artifact else None,
        "profiles": len(artifact.get("handles", [])) if artifact else 0,
        "trained_at": artifact.get("trained_at") if artifact else None,
        "version": artifact.get("version") if artifact else None,
        "recommendation_ready": artifact.get("recommendation_ready", False)
        if artifact
        else False,
    }


@app.post("/api/v1/model/train")
def train_model() -> dict:
    with store.connect() as db:
        profiles = [p for p in store.all_records(db, "profile") if not p["sample"]]
    examples = [
        e
        for p in profiles
        for e in coach.analyze(p["submissions"], time.time())["examples"]
    ]
    try:
        artifact = ml.train(examples)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    artifact["handles"] = sorted(p["handle"] for p in profiles)
    artifact["trained_at"] = time.time()
    with store.connect() as db:
        store.put(db, "model", "active", artifact)
    return {"handles": artifact["handles"], "metrics": artifact["metrics"]}
