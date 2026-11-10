# IIT Kanpur cohort evaluation

This run imported 320 real profiles selected across current rating levels from 1,574 public API profiles whose organization text exactly matched `IIT Kanpur`. The roster includes inactive and retired rated profiles. The API does not expose numeric organization ID 470, so this is a text-based cohort rather than verified membership in that numeric organization. The synthetic demo and other imported profiles did not enter this run.

## Dataset

| Item                                                         |   Count |
| ------------------------------------------------------------ | ------: |
| Successfully imported and contributing profiles              |     320 |
| Imported submissions                                         | 179,141 |
| Completed rated attempt windows                              |  87,162 |
| Final model training attempts                                |  69,729 |
| Middle validation attempts used for selecting regularization |  17,432 |
| Later final test attempts                                    |  17,433 |

Validation is a subset of the pre-test data, not an additional disjoint dataset beyond the counts above. Feature snapshots use only earlier outcomes. Expired windows count as failures; acceptance within 24 hours counts as success. Model selection fits on the earliest window and compares five regularization strengths on the middle window. The selected regularization parameter was C=100. The final model is fit on pre-test data only. Both chronological boundaries purge overlapping outcome windows.

## Final holdout results

| Predictor                   |      Accuracy | Brier score, lower is better |
| --------------------------- | ------------: | ---------------------------: |
| Logistic regression         |        91.72% |                      0.07281 |
| Constant training base rate |        91.69% |                      0.07688 |
| Topic Elo probability       | Not evaluated |                      0.28520 |

Logistic-regression log loss was 0.26557. The classifier improved Brier score modestly over the constant base rate. Accuracy barely exceeded the majority-class baseline because 91.69% of test attempts were successful. Accuracy alone should not be used to describe recommendation quality.

There were 502 test attempts in the predicted 50–70% band. Their average predicted success was 63.52%, while observed success was 71.51%. The model underestimates success in this band, and probabilities must remain labeled estimates. This evaluation does not establish performance on never-attempted problems, unseen institutions, or users outside the cohort.

## Reproduce and inspect

```sh
uv run python -m scripts.train_cohort --limit 320
uv run python -m scripts.train_cohort --limit 320 --train-only
uv run pytest -q
```

Run imports with the web server stopped to preserve the request limit across processes. The exact handles, source and import timestamps, per-profile results, and contribution counts are in ignored `data/large_training_manifest.json`. Aggregate machine-readable results are in `data/large_training_report.json`; fitted coefficients and provenance are in the local SQLite model record. No raw histories or fitted artifacts are committed.

Public API submission coverage can differ from the total on a Codeforces profile. Missing submissions cannot inform model features or labels. Problem ratings and tags reflect metadata exposed at import time and can differ from historical metadata. Observed acceptance does not establish independent solving or absence of editorial help.
