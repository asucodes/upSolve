# upSolve

A local Codeforces practice coach by **The Syndicate**. FastAPI, SQLite, and plain HTML/CSS/JavaScript. No frontend build step or CDN dependency.

## Run

Install Python 3.12 or newer and [uv](https://docs.astral.sh/uv/), then:

```sh
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Enter a public Codeforces handle or choose **Explore sample profile**. SQLite lives in ignored `data/upsolve.sqlite3`; override with `UPSOLVE_DB`. Run one server worker so imports share a single request limiter.

## Features

- **Problemset** at `/problemset`: search names and IDs, filter by topic group, Codeforces tag, rating, and profile solve status; paginate and refresh the public catalog without importing a handle.
- **Topic gym** at `/gym`: twelve curated CP topic groups, catalog progress, learning resources, and unseen warm-up/main/stretch suggestions for the selected profile. Each topic is a separate set; a multi-topic problem may appear in multiple groups.

- Today: three unseen rated problems in the estimated 50–70% solve band, with reasons.
- Insights: topic estimates and evidence, topic and official rating charts, local-time activity heatmap.
- Training: two focus topics, weekly solve target, and progress after syncing.
- Persistent queued imports, pagination, submission-ID deduplication, judging refresh, cached catalog, and failure recovery.
- Shared experimental logistic-regression training from real imported profiles, chronological holdout evaluation, and conservative topic Elo recommendations. The sample profile never enters training.

## Model and limitations

A scored attempt begins at the first eligible judged submission. Acceptance within 24 hours counts as success; an unresolved window counts once as failure after closing. Compilation errors and pending or administrative verdicts are neutral. Later attempts after an expired window can count separately; repeat solves do not add rating credit. Ratings start at 1000 and split K=32 updates over the problem tags.

Feature snapshots are computed at attempt start and cannot see later outcomes. Logistic regression uses the topic/difficulty gap, prior topic evidence, and tag count. It requires at least 50 completed real attempts and a viable chronological split with both training classes. Overlapping outcome windows are purged at the split boundary. Published metrics include accuracy, Brier score, log loss, calibration bins, and an Elo comparison. The evaluated artifact remains available for experimental analysis; recommendation eligibility is a separate gate.

These estimates describe acceptance in observed submission windows, not independent mastery or time spent. Tags do not prove which technique a user used. Current catalog difficulty and tags may differ from historical metadata. Never-attempted problems have no observed outcome. Missing rated candidates produce an empty state rather than silently widening the probability band. New topics remain provisional until five distinct problems provide evidence.

### Recommendation correction

The trained classifier remains an **experimental acceptance model**, visible in Insights, and is not enabled for recommendations by current training artifacts. Its training target is acceptance among self-selected submitted attempts within 24 hours, not the chance that a user independently solves an unseen task. The large holdout has a 91.69% success rate; treating those probabilities as independent ability produced implausible 1700–2100 recommendations for a roughly 1000-rated user. More cohort profiles alone cannot fix that target mismatch.

Practice suggestions currently use explicitly uncalibrated topic Elo heuristics. Sparse topic estimates shrink toward the current official rating (1000 provisional reference for unrated users). Rounded-down current rating, with a minimum catalog level of 800, sets the warm-up ceiling; main and stretch add 100 and 200 points. Roles are assigned by the backend, never by row position. A missing slot stays missing rather than receiving an unsuitable harder problem. The 50–70% figures are heuristic match scores, not empirically validated independent solve probabilities. A learned model needs a suitable target, matching feature preprocessing, and profile-aware calibration before being marked recommendation-ready.

Topic groups are curated mappings to Codeforces tags informed by the [CP-Algorithms topic index](https://cp-algorithms.com/) and [USACO Guide resources](https://usaco.guide/general/resources-cp). We link to learning materials rather than copying tutorial content. The gym is not a contest/judge and the categories do not imply an official USACO curriculum or division mapping.

The solved counter counts distinct accepted problems in public `user.status` submissions, including unrated problems. It is labeled **Problems solved (public API)** because this source can differ from the total displayed on the Codeforces profile. The dashboard links to that profile and reports the imported submission count; it does not invent missing submissions or use a reported profile total as training evidence.

## IIT Kanpur training cohort

With the web server stopped, run:

```sh
uv run python -m scripts.train_iitk --limit 8
```

The user-approved source is the [IIT Kanpur organization ranking](https://codeforces.com/ratings/organization/470/page/1). Since the webpage blocks automated requests, the importer uses the official `user.ratedList` API and exact organization text `IIT Kanpur`. The API does not expose numeric organization membership; this is an explicit text-based cohort, not a verified scrape of organization ID 470. It chooses active profiles evenly across current rating levels rather than only top-ranked users. A manifest records source, selected handles, import timestamps, failures, and selection ratings in ignored `data/training_manifest.json`. Only successfully imported real cohort profiles enter this training run. Raw histories and fitted coefficients stay in the local SQLite database.

This cohort can be useful for the local demo but is not representative of every Codeforces user. Evaluation reports later outcomes within the cohort, not generalization to unseen institutions or users.

### Larger resumable training run

```sh
uv run python -m scripts.train_cohort --limit 320
```

Stop the web server before importing so live syncs do not compete with the training process's API request limiter. This uses active, inactive, and retired exact-organization matches and spans rating levels. Completed imports less than seven days old are reused. Partial pages are checkpointed; a resumed partial import scans from the newest page again to avoid mistaking an incomplete history for a completed one. Per-profile failures, source details, progress, and contribution counts are written to ignored `data/large_training_manifest.json`. At least 300 profiles must contribute completed rated attempts before a large run replaces the active model. Increase `--limit` if needed to compensate for empty profiles or failures.

Use `--train-only` to repeat model fitting from completed local imports, or `--refresh-roster` to refresh the roster. Model selection compares five regularization strengths on a middle chronological validation window. The final 20 percent time window is untouched until evaluation; overlapping outcome windows are purged at both boundaries. Metrics include class-balance baselines and calibration in the 50–70 percent recommendation band. The evaluated model, not an unevaluated full-data refit, replaces the latest experimental artifact. It is not automatically enabled for recommendations. Aggregate results are saved to ignored `data/large_training_report.json`. Raw histories, personal profile data, manifests, and fitted models stay out of Git.

## Partner REST API

Interactive OpenAPI docs: http://127.0.0.1:8000/docs. Schema: `/openapi.json`.

New browsing endpoints:

| Method | Endpoint                        | Purpose                                                                                                                                                |
| ------ | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| GET    | `/api/v1/problems`              | Paginated search with `handle`, `search`, `category`, `tag`, `minimum`, `maximum`, `state`, `sort`, `include_unrated`, `page`, and `page_size` filters |
| POST   | `/api/v1/problems/refresh`      | Refresh the public catalog, preserving cached problems on failure                                                                                      |
| GET    | `/api/v1/practice/topics`       | Curated topic groups, CF tags, and learning-resource URLs                                                                                              |
| GET    | `/api/v1/profiles/{handle}/gym` | Profile-based topic sets, progress, rating reference, and difficulty-bounded suggestions                                                               |

| Method | Endpoint                              | Purpose                                                       |
| ------ | ------------------------------------- | ------------------------------------------------------------- |
| POST   | `/api/v1/sync`                        | Start or reuse a sync job; body `{"handle":"your_handle"}`    |
| GET    | `/api/v1/sync/{id}`                   | Poll queued, running, complete, or failed job                 |
| GET    | `/api/v1/profiles`                    | List imported profiles                                        |
| GET    | `/api/v1/profiles/{handle}/dashboard` | Profile, topics, history, activity, recommendations, and plan |
| PUT    | `/api/v1/profiles/{handle}/plan`      | Save `{"topics":["dp"],"target":5}`                           |
| GET    | `/api/v1/topics`                      | Available catalog topics                                      |
| POST   | `/api/v1/model/train`                 | Train/evaluate from all imported real profiles                |
| GET    | `/api/v1/model`                       | Model availability and evaluation metrics                     |
| POST   | `/api/v1/demo`                        | Load synthetic sample, isolated from live catalog             |

The partner app runs separately and consumes REST. Set `UPSOLVE_CORS_ORIGINS=http://localhost:3000` (comma-separated exact origins) to allow its frontend. Default CORS permits no cross-origin frontend. No login or authorization is provided: keep the service bound to loopback. Training settings are shared by handle within this local installation. The partner plugin's own concept and API remain pending agreement.

## Test

```sh
uv run pytest -q
```

Tests use temporary SQLite files and mocked Codeforces transport. The sample is synthetic, its problem links are disabled, and its contest-rating chart is intentionally empty. No live profile data, model artifacts, virtual environments, or SQLite files belong in Git.
