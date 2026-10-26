# Testing

## The verification loop

Verification runs at three levels. Each level is a make target, and CI runs the same targets.

| Level | When | Command | What it proves |
|---|---|---|---|
| Inner | After every change | `make test` | Unit, API, scenario, invariant and golden tests pass. |
| Commit | Before every commit | `make verify` | The tests pass, the live server answers correctly, latency meets the target, and the README's results are current. |
| Release | Before sending the link | `make fresh-check` | A clean clone works by following the README alone. |

CI runs `make setup` and `make verify` on every push, on Ubuntu with Python 3.11 and 3.12.

## Test layers

Every test name starts with its ID from the plan, so `.venv/bin/python -m pytest -k f1` runs one rule's tests.

| File | IDs | What it covers |
|---|---|---|
| tests/test_seed.py | D1 to D4 | Seeding is repeatable, tags are normalized, free-form tags load, and user lookups use the primary key index. |
| tests/test_models.py | D5, D6 | User lookups, the snapshot time, and every catalog feature recomputed from the raw JSON. |
| tests/test_profile.py | P1 to P4 | Interest weights by source, the six generic bios, and the strategy split across all users. |
| tests/test_recommender.py | F1 to F3, R1 to R9 | Gates, relevance, activity, reach, capacity, grouping, backfill, cold start and tie-breaking. |
| tests/test_explain.py | X1 to X6 | Every reason code's copy, the copy rules across all users, and swapping the explainer. |
| tests/test_api.py | A1 to A6 | Endpoints, the response contract, validation, errors, the debug view and startup seeding. |
| tests/test_scenarios.py | S1 to S5 | The four planted scenarios from the dataset README, and the golden snapshot. |
| tests/test_invariants.py | I1 to I5, B1 | Rules checked for every one of the 100 users, and a timing bound. |

The suite has 566 tests and runs in under a second. Most of them are the invariant tests, which run once for each of the 100 users.

## The smoke test

`make smoke` starts the API as a real process on a free port, against a database that doesn't exist yet, so startup has to seed it. It then checks:

| Request | Expected |
|---|---|
| The root URL | A redirect to /docs |
| Health check | 200 |
| User 7's recommendations | #5 and #6 first |
| User 15's recommendations | At most one of #10, #11 and #12 |
| User 23's recommendations, with the debug flag | #22 first, with #20 and #21 listed as excluded |
| User 42's recommendations | Cold-start strategy, with a nudge |
| User 999 | 404 |
| A limit of 0 | 422 |

The server stops whether the checks pass or fail.

## The fresh-clone check

`make fresh-check` clones the committed repo into a temporary folder and runs `make setup`, `make test` and `make smoke` there. It proves the README's setup steps work on their own, and it catches files that exist locally but were never committed. Uncommitted changes aren't part of the check, and it prints a note when there are any.

## Breaking it on purpose

Each key rule was disabled once, in a scratch copy of the repo, to confirm the right tests fail.

| Rule disabled | Tests expected to fail | Tests that failed |
|---|---|---|
| Full gate | F1, I1, S3 | A5, F1, F3, I1, S3 |
| Inactive gate | A5, F2 | A5, F2, F3, I1 |
| Topic grouping | I3, R7, S2 | A2, I3, R7, R8, S1, S2, S5 |
| Location multiplier | R5, S5 | A2, R5, S1, S4, S5, X6 |
| Bio interests | P1 | P1, P2, P4, X2 |
| Posting members in the activity score | R3, R4 | R3, R4, S5, X2 |

The first run found a gap. With the full gate off, S3 still passed. The full Circle #20 shares #22's topic, so grouping folded it under #22 as a similar Circle, and S3 only checked listed results. Similar Circles are shown to members, so S3 and I1 now check them too. The table shows the run after that fix.

## Testing by hand

Start the server with `make run`, then open http://127.0.0.1:8000/docs to try requests in the browser, or use curl:

```bash
curl -s http://127.0.0.1:8000/users/42/recommendations                         # cold start
curl -s http://127.0.0.1:8000/users/7/recommendations                          # obvious matches
curl -s http://127.0.0.1:8000/users/15/recommendations                         # duplicate Circles
curl -s "http://127.0.0.1:8000/users/23/recommendations?include_excluded=true"  # full or inactive
curl -s http://127.0.0.1:8000/users/999/recommendations                        # 404
```

`make scenarios` prints the four planted scenarios without a server. `make report` writes every user's results to `reports/recommendations.md` for a manual read.

## Changing the ranking on purpose

The golden snapshot in `tests/golden/planted.json` pins the top five for users 7, 15, 23 and 42. When a change moves them on purpose:
1. Run `make golden` to record the new results.
2. Run `make docs` to refresh the README's results block.
3. Review both diffs, and say why the ranking changed in the commit message.

## Troubleshooting

- **A stale database.** Tests and scripts always seed their own temporary database. Only `make run` uses `circles.db`, and `make seed` rebuilds it.
- **A busy port.** `make run PORT=8001`. The smoke test picks a free port by itself.
- **Python older than 3.11.** `make setup` stops with the version it found. Run `make setup PYTHON=python3.12` with a newer interpreter.
