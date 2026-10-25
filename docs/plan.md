# Implementation plan: Lean In Circle recommender

**Status, 2026-10-24.** Committed: project setup, dataset notes, the SQLite schema and the seed script. Written but not committed: the data access layer, the inspection script, this plan and the decision log. Still to build: the recommender, the API, the Makefile, tests and docs.

**Decisions.** [decision-log.md](decision-log.md) records decisions made during implementation, with the evidence behind each.

**Validated.** A throwaway prototype of the ranking passes all four planted scenarios. All 100 users get five results on five different topics, and none breaks a rule. Ranking takes 0.07 ms per user.

**Budget.** The assignment asks for 3 to 4 hours at most. The remaining work is estimated at about 3 hours 20 minutes, including verification. If that would take the total past 4 hours, section 3 lists what to cut first.

---

## 1. Requirements

### From the assignment

- **Mission.** Lean In is "the largest community dedicated to advancing women's leadership - more than 170,000 Circles in 180+ countries." Women in Circles "are nearly twice as likely to be promoted." connect.leanin.org is built to reach millions of women.
- **The ask.** "Build an API that returns a ranked list of Circles for a given user, along with a short, member-facing explanation for each recommendation." It must return "sensible recommendations for every user in the dataset."
- **Signals.** "The signals you choose and your rationale for choosing them are part of what we'll evaluate."
- **Criteria.** Product sense, engineering craft, judgment, mission awareness and AI fluency. Mission awareness asks about "the needs of members looking for relevant, active Circles". AI fluency asks you to "explain and defend the decisions reflected in your submission".
- **Time.** No more than 3 to 4 hours. Anything left goes in the design doc.

### Deliverables

Every deliverable has a check that proves it works.

| Deliverable | Where | Verified by |
|---|---|---|
| API, runnable locally | app/ | API tests and the live smoke test |
| Clear setup instructions | README.md | The fresh-clone check and CI, which run the README's own commands |
| Makefile | Makefile | The fresh-clone check and CI |
| Database schema, with relationships, indexing decisions and rationale | app/schema.sql, docs/SCHEMA.md | Data-layer tests, including a query-plan check |
| One-page technical design doc: what was built, tradeoffs, production scale, what to explore with more time | docs/DESIGN.md | Word count in the release checklist |
| Decision log and AI notes | docs/decision-log.md, docs/AI_NOTES.md | The release checklist |

### From the dataset README

- A Circle is full when member_count reaches max_members. A null max_members means uncapped.
- Activity combines feed_posts_30d, last_activity_at, chat_messages_30d and engagement in activity.json, weighted as we see fit.
- A Circle's leaders and their profiles come from memberships with the leader role, joined to users.
- Tags are "free-form topic-ish tags", and some Circles have no topic.
- "Topic overlap and the fields above are enough for this exercise." Embeddings aren't expected.
- Chat text is withheld "for privacy realism".
- The planted records will be run against the submission: "be ready to talk through them".

### Planted scenarios

| Scenario | User | Trap | What good looks like |
|---|---|---|---|
| Cold start | 42 | No interests, bio, memberships or location. Joined a day before the snapshot. | Five open, active, hybrid or virtual Circles on five topics, plus a nudge to add interests. |
| Obvious matches | 7 | Interested in leadership skills and public speaking. Lives in Seattle. | #5 Women Who Lead and #6 Speak Up Circle at ranks 1 and 2. |
| Duplicate Circles | 15 | #10, #11 and #12 are near-identical negotiation Circles. | One negotiation Circle in the list, with the other two attached to it as similar Circles. |
| Full or inactive | 23 | #20 is full. #21 is inactive and also unlisted. | #22 Level Up Collective at rank 1. #20 and #21 are absent, and the debug view says why. |

### What this means for the recommender

- **An unavailable Circle is a broken promise.** Full, inactive and unlisted Circles never rank. A member who joins a dead Circle gets no support and may not try again.
- **Capacity is pass/fail.** Only a full Circle is affected. Spots left don't change rank.
- **Active means a community, not a broadcast.** Count how many members post and how much response their posts get, not just volume.
- **Members have to be able to attend.** The leader's city stands in for the Circle's location, and reachable Circles rank higher. Virtual and hybrid Circles stay open to everyone.
- **Use everything the member has told us.** Stated interests come first, then the bio, then the Circles they're in. Only a member with none of these gets the cold-start list.
- **Explain in the member's terms.** Say why it fits, that it's active and how to join, using only facts from the data.
- **Give real choices.** Never spend two slots on near-identical Circles.

---

## 2. Design

### Scope

**Must have**
- The recommendations endpoint, a health check, interactive docs, and a debug view of excluded Circles.
- An interest profile built from stated interests, bio keywords and memberships.
- Eligibility gates, scoring, topic diversity and cold start.
- Template explanations behind an explainer interface.
- A Circle catalog cached at startup, plus a benchmark script.
- Schema fixes: free-form tags, and no redundant index.
- A Makefile and README setup instructions, both exercised by the fresh-clone check and CI.
- Tests at every layer, a live smoke test, CI on every push, and pinned dependencies.
- README, DESIGN.md, SCHEMA.md, TESTING.md and AI_NOTES.md.

**Out of scope, listed under "with more time" in DESIGN.md**
- LLM-written explanations, precomputed offline as described below.
- Matching on post text, once real posts carry topic signal.
- Co-membership signals, such as "members of your Circles also joined".
- Learning from impressions and joins, and A/B tests.
- Capacity-aware allocation, waitlists, and a "start a Circle" prompt when nothing fits.
- Time zones and language for virtual Circles, and a real location field for Circles.
- Auth, rate limits and pagination.

### Ranking pipeline

Ranking is pure Python in app/recommender.py. Copy lives in app/explain.py, and all SQL stays in app/models.py.

1. **Snapshot time.** "Now" is the latest timestamp in the data, 2026-09-21. Today's date would make every Circle look idle. An environment variable can override it.
2. **Catalog.** Built once at startup. For each Circle it holds:
   - normalized tags;
   - the leader's city, left empty for no city or "Remote";
   - idle days, counted from the later of last_activity_at and the newest post, because circle 32's newest post is newer than its last_activity_at;
   - for the 30 days before the snapshot: distinct members posting, the leader's share of posts, and reactions plus comments per post.
3. **Interest profile.** A member with no source at all gets cold start.

   | Source | Weight | When it applies |
   |---|---|---|
   | Stated interests | 1.0 | Always |
   | Bio keywords | 0.6 | Topics not already stated |
   | Topics of the member's Circles | 0.4 | Only when there are no stated interests |

4. **Gates.** A Circle is excluded if the member already belongs to it, or if it's unlisted, full, or idle for 60 days or more. Every reason is recorded.
5. **Score.**
   - Personalized: (0.6 × relevance + 0.4 × activity) × reach.
   - Cold start: (0.85 × activity + 0.15 for an open join policy) × reach.
   - Relevance: the matching source's weight for a topic match, half that for a tag-only match, plus 0.1 for each extra matched interest, capped at 1.
   - Activity: four equal parts. Recency decays over 14 days. Volume is 60% posts and 40% chat, capped at 12 posts and 100 messages. Engagement is capped at 15 reactions and comments per post. Participation is capped at 8 members posting, and halves when the leader writes over 80% of posts.
   - Reach multipliers:

     | Format and city | Multiplier |
     |---|---|
     | In person, same city | 1.15 |
     | Hybrid, same city | 1.10 |
     | Virtual, or hybrid elsewhere | 1.00 |
     | In person, city unknown | 0.80 |
     | In person, another city | 0.40 |

   - Equal scores break ties by Circle id, so results are deterministic.
6. **Diversity.** Circles with the same primary topic form a group. The best one is listed and the rest are attached to it as similar Circles. If there are fewer groups than slots, the list backfills from the attached ones. Circles with no topic never group.
7. **Explanations.** See the next section.

Tests check behavior, such as order, inclusion and copy rules, rather than exact weights, so tuning stays cheap. Only the golden snapshot changes when weights change, and it's updated on purpose.

### Explanations

Each result gets three sentences, one per slot, in at most 200 characters.

**Slot 1: why it fits**

| Code | When | Template |
|---|---|---|
| interest_topic | The Circle's topic is a stated interest | Focused on {topic}, one of your interests. |
| interest_multi | It matches two or more stated interests | Covers {topic} and {topic}, both on your list. |
| interest_tag | A tag matches a stated interest, but the topic doesn't | Also covers {topic}, one of your interests. |
| bio_match | The match came from the bio | Fits what you wrote in your bio about {topic}. |
| circle_match | The match came from a Circle the member is in | Similar focus to {circle}, a Circle you're in. |
| popular | No match, at cold start | One of the most active Circles right now. |
| explore | No match, in a filler slot for a member with interests | A change of pace from the topics in your profile. |

**Slot 2: why it's active.** The first row that applies wins.

| Code | When | Template |
|---|---|---|
| members_posting | 5 or more members posted in 30 days | {n} members posted in the last 30 days. |
| busy | 8 or more posts in 30 days | {n} posts in the last 30 days. |
| active_week | Idle 7 days or less | Active this week. |
| active_month | Idle 30 days or less | Active in the last month. |
| quiet | Otherwise | Last active {n} days ago. |

**Slot 3: how to take part.** The first row that applies wins.

| Code | When | Template |
|---|---|---|
| request_to_join | The join policy is request | Request to join; the leader approves new members. |
| near_you | In person or hybrid, with the leader in the member's city | Led from {city}, close to you. |
| virtual | Virtual | Meets virtually, so you can join from anywhere. |
| hybrid | Hybrid, led from elsewhere | Hybrid, so you can join online. |
| in_person_far | In person, with the leader in another city | Meets in person, led from {city}. |
| in_person | In person, city unknown | Meets in person. |

**Nudge.** One message per response, not per result.

| Strategy | Nudge |
|---|---|
| personalized | None |
| inferred, from bio or Circles | Add a few interests to your profile for more personal picks. |
| cold_start | Add a few interests to your profile and we'll tailor these picks to you. |

**Examples from the prototype data**
- User 7, #5: "Focused on Leadership skills, one of your interests. 8 members posted in the last 30 days. Led from Seattle, WA, close to you."
- User 7, #6: "Covers Public speaking and Leadership skills, both on your list. 5 members posted in the last 30 days. Meets in person."
- User 23, #22: "Focused on Getting promoted, one of your interests. 5 members posted in the last 30 days. Request to join; the leader approves new members."
- User 42, #11: "One of the most active Circles right now. 8 members posted in the last 30 days. Hybrid, so you can join online."

**Copy rules**
- Topic labels, never slugs.
- Every number comes straight from the data.
- No scores, weights or mentions of an algorithm.
- No quotes from posts or bios. The only profile detail shown is the leader's city.
- The same input always gives the same text.

**The LLM path, designed but not built**
- Copy comes through an explainer interface. The template explainer is its only implementation in P0, and each response reports "template" as its explanation source.
- Later, a batch job would precompute warmer copy for each Circle and reason combination, using a hosted model such as OpenAI's. Requests would read the stored copy and fall back to templates, so latency wouldn't change.
- The model would see only reason codes and their facts. Output would be checked for length, a topic mention and no new numbers, with the template as the fallback.
- The key would come from an environment variable or an uncommitted .env file. A committed .env.example lists variable names only. The current .gitignore excludes .env.example along with other .env files, so it needs an exception line.
- Tests use a fake explainer, so CI never calls the network and reviewers need no key.

### Performance

- **Target:** a 95th-percentile response under 50 ms on a laptop.
- **Prototype numbers:** building the catalog takes 0.5 ms, once. Ranking takes 0.07 ms per user. HTTP and JSON handling will dominate.
- **Per request:** three indexed lookups for the member, ranking of 40 cached Circles, and template copy. No network calls.
- **Freshness:** the catalog is built at startup, so restart the server after reseeding.
- **Measurement:** `make bench` sends every user through the app in process and prints p50 and p95. It fails above the target, so `make verify` catches regressions. A test also asserts that ranking all 100 users takes under a second, which catches accidental per-Circle queries.

### Signals

| Signal | How it's used | Why |
|---|---|---|
| Stated interests | Relevance, at weight 1.0 | The member said what they want. |
| Bio | Relevance through keywords, at weight 0.6 | The member's own words. 12 more members get personal picks. |
| Memberships | Circles the member is in are excluded. Their topics weigh 0.4 when there are no stated interests. | Never re-recommend. A member's Circles hint at their interests. |
| Circle topic and tags | Matched against the interest profile | The structured content signal. |
| Access | Unlisted Circles are excluded | Unlisted Circles are invite-only by intent. |
| Capacity | Full Circles are excluded. Otherwise ignored. | Pass/fail. Spots left don't change whether anyone can join. |
| Last activity and newest post | Inactive at 60 or more idle days. Recency is part of the score. | A dead Circle can't support anyone. |
| 30-day posts and chat | Volume, in the score | Raw activity. |
| Engagement and posting members in activity.json | Engagement and participation, in the score | A community, not a broadcast. |
| Post text in activity.json | Not used | Measured: no topic signal in this dataset. Also a privacy concern. |
| Format and leader's city | Reach multiplier and copy | Members have to be able to attend. |
| Join policy | Copy, plus a small cold-start preference for open Circles | Sets expectations. Penalizing it would bury #22. |
| Member count | Only for the full check | Size isn't quality. |
| Profile completeness and join date | Not used for ranking | They measure profile effort and tenure, not what the member wants. |
| Job title, company and industry | Not used | No Circle-side field to match, and a risk of stereotyping. |
| Photo and cover image | Cover URL returned for display only | Cosmetic. |

### API contract

```
GET /health                              -> {"status": "ok"}
GET /users/{user_id}/recommendations
      ?limit=5                           1 to 20, otherwise 422
      &include_excluded=false            debug: list excluded Circles with reasons
Unknown user                             -> 404 {"detail": "User 999 not found"}
Interactive docs                         -> /docs
```

```json
{
  "user_id": 23,
  "as_of": "2026-09-21T00:00:00Z",
  "strategy": "personalized",
  "profile_nudge": null,
  "explanation_source": "template",
  "recommendations": [
    {
      "rank": 1,
      "score": 0.933,
      "circle": {
        "id": 22, "name": "Level Up Collective", "topic": "getting-promoted",
        "topic_label": "Getting promoted", "format": "hybrid", "join_policy": "request",
        "member_count": 14, "max_members": 20, "spots_left": 6, "cover_image_url": "..."
      },
      "explanation": "Focused on Getting promoted, one of your interests. 5 members posted in the last 30 days. Request to join; the leader approves new members.",
      "reasons": [
        {"code": "interest_topic", "text": "Focused on Getting promoted, one of your interests."},
        {"code": "members_posting", "text": "5 members posted in the last 30 days."},
        {"code": "request_to_join", "text": "Request to join; the leader approves new members."}
      ],
      "similar_circles": []
    }
  ],
  "excluded": [
    {"circle_id": 20, "name": "The Promotion Path", "reasons": ["full"]},
    {"circle_id": 21, "name": "Career Climbers", "reasons": ["unlisted", "inactive"]}
  ]
}
```

- Strategy is "personalized" for stated interests, "inferred" for bio or memberships, or "cold_start".
- The score is for debugging and isn't meant for display.
- The excluded list is null unless the debug flag is on.
- The app seeds the database at startup if the file is missing, so the server runs straight after setup.
- An environment variable sets the database path, and tests point it at a temporary file.

### Tradeoffs

| Decision | Alternative | Why |
|---|---|---|
| Weighted rules | ML or learning to rank | There's no click or join data to learn from. Rules are explainable and testable in the time. |
| Templates behind an interface | An LLM at request time | Deterministic, free, adds no latency and needs no keys. An LLM can be added offline later. |
| Gates for unavailable Circles | Penalties | Showing them breaks the promise. The debug view keeps them inspectable. |
| Location as a multiplier | A hard filter | The leader's city is only a proxy, and a filter would hide valid Circles. |
| A keyword list for bios | NLP or embeddings | The README says topic overlap is enough. Keywords are transparent and testable. |
| No matching on post text | Keywords from posts | Measured: post text carries no topic signal here. |
| Group by topic and attach similar Circles | Embedding dedupe, or a soft penalty | Fits the taxonomy, is easy to explain, and keeps alternatives visible. |
| Snapshot time from the data | Wall-clock time | The data is frozen on 2026-09-21. |
| Catalog cached at startup | Queries on every request | There are 40 Circles. Production would refresh the catalog with a job. |
| Ranking in pure Python | Scoring in SQL, or an ORM | Unit tests need no database, and the logic reads top to bottom. |

---

## 3. Commit plan

Commits go straight to main. Each one is small and leaves the tests passing. From commit 4 on, CI runs on every push.

| # | Commit | Contents | Tests | Estimate |
|---|---|---|---|---|
| 1 | `feat(data): data access layer` | app/models.py, already written | | 2 min |
| 2 | `chore: dataset inspection script` | scripts/inspect_data.py, already written, plus the review's evidence checks | | 5 min |
| 3 | `docs: implementation plan and decision log` | docs/plan.md, docs/decision-log.md | | 1 min |
| 4 | `build: Makefile, pinned dependencies, pytest config and CI` | Makefile with help, setup, seed, test and clean; pinned requirements; pytest markers; a CI workflow running `make setup test` on Python 3.11 and 3.12; .env.example with its .gitignore exception | | 15 min |
| 5 | `fix(schema): free-form tags and no redundant index` | schema.sql, tag normalization in seed.py | D1 to D4 | 10 min |
| 6 | `feat(data): Circle catalog with 30-day participation` | Catalog query and snapshot time in models.py | D5, D6 | 15 min |
| 7 | `feat(recommender): interest profile` | Bio keyword list, membership topics, cascade | P1 to P4 | 15 min |
| 8 | `feat(recommender): gates and scoring` | Gates with reasons, relevance, activity, reach | F1 to F3, R1 to R6 | 20 min |
| 9 | `feat(recommender): diversity and cold start` | Grouping, similar Circles, backfill, cold start | R7 to R9 | 15 min |
| 10 | `feat(explain): templates and explainer interface` | Reason codes, templates, nudge | X1 to X6 | 20 min |
| 11 | `feat(api): recommendations endpoint` | App factory, startup catalog, response models, debug view, `make run` | A1 to A6 | 20 min |
| 12 | `test: scenarios, invariants and the verification loop` | Scenario, smoke, benchmark and fresh-clone scripts; the make targets for them; CI switches to `make setup verify` | S1 to S5, I1 to I5, B1 | 25 min |
| 13 | `docs: README, design, schema, testing and AI notes` | Five docs; the README's results block and `make docs`; `make verify` starts checking that block | | 35 min |

The estimates add up to about 3 hours 20 minutes, including running the verification loop on every commit. The prototype already contains the ranking logic, which shortens commits 7 to 9.

**Cut list, in order, if time runs short**
1. The benchmark script. Keep the timing test.
2. The Python 3.11 CI job. Keep 3.12, and state the tested version in the README.
3. Membership topics. Those 17 members get the cold-start list instead.
4. SCHEMA.md. Fold it into a section of DESIGN.md.

**Never cut:** the Makefile, the setup instructions, the smoke test, the fresh-clone check, and the scenario and invariant tests.

**Target layout**

```
Makefile
app/
  main.py          FastAPI app, routes, startup catalog and seeding
  schemas.py       Pydantic response models
  config.py        database path and snapshot-time override
  recommender.py   interest profile, gates, scoring, diversity, cold start
  explain.py       reason codes, templates, explainer interface
  models.py        all SQL
  seed.py          JSON to SQLite
  schema.sql       tables and indexes
scripts/
  inspect_data.py  dataset and review checks
  scenarios.py     prints scenarios; writes the README block, the report and the golden file
  smoke.py         starts the real server and checks key endpoints
  benchmark.py     p50 and p95 latency over all users
  fresh_check.sh   clones the committed repo and runs setup, test and smoke
tests/
  conftest.py  test_seed.py  test_models.py  test_profile.py  test_recommender.py
  test_explain.py  test_api.py  test_scenarios.py  test_invariants.py
  golden/planted.json
docs/
  DESIGN.md  SCHEMA.md  TESTING.md  AI_NOTES.md  decision-log.md  data-notes.md  plan.md
.github/workflows/tests.yml
.env.example
```

---

## 4. Makefile and setup instructions

Both are deliverables. A reviewer should get from a fresh clone to a running API with two commands, and those commands run on every push.

### Makefile targets

| Target | What it does |
|---|---|
| `make help` | Lists every target. This is the default. |
| `make setup` | Checks for Python 3.11 or newer, creates .venv and installs the pinned requirements. |
| `make seed` | Rebuilds circles.db from data/. |
| `make run` | Starts the API on port 8000, or on PORT if it's set. Docs are at /docs. |
| `make test` | Runs the whole test suite. |
| `make scenarios` | Prints the four planted scenarios as markdown. |
| `make docs` | Rewrites the README's results block from the current scenarios. |
| `make report` | Writes every user's recommendations to reports/, which git ignores, for a manual read. |
| `make golden` | Accepts the current planted results as the new golden snapshot. |
| `make smoke` | Starts the real server, checks key endpoints, then stops it. |
| `make bench` | Prints p50 and p95 latency over all users, and fails above 50 ms. |
| `make verify` | Runs test, smoke and bench, and checks that the README's results block is current. |
| `make fresh-check` | Clones the committed repo into a temporary folder and runs setup, test and smoke there. |
| `make clean` | Removes .venv, circles.db, reports and caches. |

**Rules**
- Every target calls the virtual environment's Python directly, so nobody has to activate anything.
- `make setup` fails with a clear message if Python is older than 3.11.
- The targets need only Python and make. Both come with macOS developer tools and most Linux distributions. On Windows, use WSL or the plain commands in the README.
- CI calls the same targets the README tells reviewers to use, so the instructions can't drift from what's tested.

### README setup section

In this order:
1. **Prerequisites:** Python 3.11 or newer, git and make.
2. **Quickstart:** clone the repo, then run `make setup` and `make run`.
3. **A first request:** open http://127.0.0.1:8000/docs, or request user 7's recommendations with curl. The first result should be Women Who Lead.
4. **Tests:** `make test`, and `make verify` for the full loop.
5. **Without make:** the plain commands each target runs.
6. **Troubleshooting:** Python too old, port 8000 already in use, or a stale database.

```bash
git clone <repo-url>
cd leanin-circle-recommender
make setup
make run    # API at http://127.0.0.1:8000, docs at /docs
make test   # in a second terminal
```

---

## 5. Verification loop

Verification runs at three levels. Each level is a make target, and CI runs the same targets.

| Loop | When | Command | What it proves | Time |
|---|---|---|---|---|
| Inner | After every change | `make test` | Unit, API, scenario, invariant and golden tests pass. | Seconds |
| Commit | Before every commit | `make verify` | The tests pass, the live server answers correctly, latency meets the target and the README's results are current. | Under a minute |
| Release | Before sending the link | `make fresh-check` and the release checklist | A clean clone works by following the README alone. | A few minutes |

**CI** runs `make setup verify` on every push, on Ubuntu with Python 3.11 and 3.12. That covers the README's minimum version and the version used locally.

### Every commit

1. Write the tests for the commit's IDs first, from this plan, not from the code.
2. Make the change.
3. Run `make test` until it passes.
4. Run `make verify`.
5. If the golden snapshot fails, decide whether the change is intended. If it is, run `make golden` and give the reason in the commit message. If not, fix the code.
6. Read the diff for scope creep, dead code, debug output, secrets and stray data files.
7. Update any doc the change affects, in the same commit.
8. Commit, push and confirm CI passes.

### What the smoke test checks

`make smoke` starts the API as a real process on a free port and waits for the health check. It stops the server whether the checks pass or fail. Unlike the in-process API tests, it proves that `make run` starts, seeds and serves.

| Request | Expected |
|---|---|
| Health check | 200 |
| User 7's recommendations | 200, with #5 and #6 first |
| User 15's recommendations | At most one of #10, #11 and #12 |
| User 23's recommendations, with the debug flag | #22 first, with #20 and #21 listed as excluded |
| User 42's recommendations | Cold-start strategy, with a nudge |
| User 999 | 404 |
| A limit of 0 | 422 |

### Guardrails for AI-written code

- **Show the output.** A change isn't done until its test output has been shown, not just described.
- **Independent expectations.** Test expectations come from this plan's test IDs and the dataset README's scenarios, never from reading the implementation.
- **Break it on purpose.** Disable each key rule once and confirm that the right tests fail. TESTING.md records the results.

  | Rule disabled | Tests that must fail |
  |---|---|
  | Full gate | F1, S3, I1 |
  | Inactive gate | F2, A5 |
  | Topic grouping | R7, S2, I3 |
  | Location multiplier | R5, S5 |
  | Bio interests | P1 |
  | Posting members in the activity score | R3, R4 |

- **Data first.** A new heuristic is checked against the data before it's built, as the bio and post-text checks were.
- **Log decisions.** Decisions made along the way go in the decision log, with their evidence.

### Release checklist

Run these before sending the link.
- `make fresh-check` passes. It clones only what's committed, so it catches files that exist locally but were never committed. The data access layer is in that state today.
- CI is green on main for both Python versions.
- `make report` has been read: the four planted users plus ten others picked at random, read the way a member would.
- DESIGN.md fits on one page, at about 650 words or fewer.
- Nothing secret is committed: no keys, no .env file and no circles.db.
- Every commit's author email is one you're happy to publish. See section 9.

---

## 6. Test plan

Three safeguards keep new features from breaking existing behavior:
- **Invariants across all 100 users** catch a broken rule anywhere, not only in the planted cases.
- **A golden snapshot** of the planted users' top five makes any ranking change visible. `make golden` updates it on purpose.
- **CI** runs the whole loop on every push.

Shared fixtures: a seeded database in a temporary folder, a test client pointed at it, a fixed snapshot time, and factory helpers that build users and Circles for unit tests.

**Data layer**, in test_seed.py and test_models.py
- D1: Seeding twice gives identical row counts.
- D2: Tags are trimmed, lowercased and deduplicated, so circle 17 ends up with two tags.
- D3: A tag outside the taxonomy seeds without error, and the foreign key check stays clean.
- D4: A user lookup on memberships uses the primary key's index, which guards the dropped index.
- D5: An unknown user returns None. User 42 has no interests and no memberships.
- D6: Catalog features match activity.json for the 30 days before the snapshot: posts, distinct posters, leader share and engagement per post.

**Interest profile**, in test_profile.py
- P1: Stated interests weigh 1.0, new bio topics 0.6 and membership topics 0.4.
- P2: Membership topics apply only when there are no stated interests.
- P3: The keyword list maps each of the six generic bios as expected. "Career changer, ex-consultant, now in tech." maps to nothing.
- P4: A member with no interests, bio or memberships gets an empty profile and the cold-start strategy.

**Gates**, in test_recommender.py
- F1: A Circle is full when member_count reaches max_members, and never full when max_members is null.
- F2: A Circle is inactive at 60 idle days but not at 59. Idle time uses the newer of last_activity_at and the newest post.
- F3: Joined and unlisted Circles are excluded, and every reason is recorded, so circle 21 gets both unlisted and inactive.

**Ranking**, in test_recommender.py
- R1: At equal activity, a topic match beats a tag-only match, which beats no match.
- R2: All else equal, a stated interest beats a bio topic, which beats a membership topic.
- R3: Activity rises with recency, volume, engagement and posting members, and stays between 0 and 1.
- R4: A Circle where the leader wrote most posts scores lower than one with the same posts spread across members.
- R5: An in-person Circle in the member's city beats an identical virtual one. One in another city ranks below the virtual one but stays eligible. An unknown city falls between.
- R6: Below full, capacity doesn't change the score: one spot left ranks the same as ten.
- R7: Same-topic Circles produce one result with the rest attached as similar. The list backfills when there are fewer topics than slots, and Circles with no topic never group.
- R8: Cold start returns distinct topics, prefers open Circles and includes the nudge.
- R9: A member whose interests match nothing eligible still gets a full list with explore copy. Equal scores break ties by id.

**Explanations**, in test_explain.py
- X1: Each result has exactly three sentences, one per slot, in 200 characters or fewer.
- X2: Each fit source produces its own template: one stated topic, several stated interests, a tag, the bio, a membership, popular or explore.
- X3: Topic labels appear instead of slugs, and every number equals the underlying data.
- X4: A request-to-join Circle always says so.
- X5: The copy never mentions scores, weights or the algorithm, and never quotes posts or bios.
- X6: Swapping in a fake explainer changes the text and the explanation source without changing the ranking.

**API**, in test_api.py
- A1: The health check returns 200.
- A2: User 7's request returns 200, matches the response model and reports the template source.
- A3: An unknown user returns 404 with a helpful message.
- A4: A limit of 0 or 21 returns 422. A limit of 3 returns three results.
- A5: With the debug flag, user 23's response lists #20 as full and #21 as unlisted and inactive.
- A6: Startup seeds a missing database and builds the catalog once.

**Scenarios**, in test_scenarios.py with a `scenario` marker
- S1: For user 7, #5 and #6 hold ranks 1 and 2. #4 is absent because user 7 already belongs to it.
- S2: For user 15, exactly one of #10, #11 and #12 is listed, and the other two are attached to it as similar.
- S3: For user 23, #22 is at rank 1, and neither #20 nor #21 appears.
- S4: User 42 gets the cold-start strategy and five results on five topics. All are open and active, and the nudge is present.
- S5: The top-five ids for users 7, 15, 23 and 42 match tests/golden/planted.json.

**Invariants**, in test_invariants.py, run for users 1 to 100
- I1: No result is a Circle the member is in, or one that's unlisted, full or inactive.
- I2: Results are unique and ranked from 1, never exceed the limit, and scores never increase down the list. Every user in this dataset gets five.
- I3: No two results share a topic.
- I4: Every explanation follows the copy rules.
- I5: Every member with an interest signal gets a matching Circle at rank 1.

**Speed**
- B1: Ranking all 100 users takes under a second in total.

```bash
make test                               # everything
make verify                             # tests, live smoke test, benchmark, README check
make scenarios                          # print the four planted scenarios
make golden                             # accept an intended ranking change
make fresh-check                        # clone and run from scratch
.venv/bin/pytest -m scenario -v         # only the planted scenarios
.venv/bin/pytest tests/test_api.py -v   # only the API tests
```

---

## 7. Technical docs

**docs/DESIGN.md** is the required one-pager, about 600 words.
1. What I built, in three sentences, plus the pipeline in seven steps.
2. The signals and why, as a compact table.
3. Key tradeoffs, in five bullets.
4. Production scale:
   - Circle features computed by a scheduled job or from events.
   - Per-user results cached and invalidated when memberships or interests change.
   - Postgres with geo and topic indexes to find candidates across 170,000 Circles.
   - Capacity-aware allocation, so members aren't all sent to the same few Circles.
   - Impressions, join requests and 30-day retention logged as the success metric.
   - Auth, rate limits and monitoring.
5. With more time: LLM copy precomputed offline, matching on real post text, co-membership signals, learning from join outcomes, a location field for Circles, time zones for virtual Circles, and a "start a Circle" prompt when nothing fits.

**docs/SCHEMA.md** covers the schema deliverable.
- A Mermaid diagram of the seven tables and their relationships.
- Why tags and interests are join tables rather than JSON columns: matching is indexed and references are checked.
- Constraints: foreign keys, checks on fixed values, and the 0 or 1 check on has_photo.
- Each index and the query it serves.
- Two review changes: the tag foreign key was dropped because tags are free-form, and the user_id index on memberships was dropped because the primary key covers it.
- Why full, inactive and leader location are computed when read rather than stored: stored copies go stale.
- What changes in production: Postgres, a materialized Circle-features table, array or GIN indexes for tags, and partitioned activity.

**docs/TESTING.md** explains how to test.
- The verification loop and the make target for each level.
- What each test layer covers, using the IDs in section 6.
- What the smoke test checks, and what the fresh-clone check proves.
- The break-it-on-purpose results.
- Manual testing through the interactive docs at /docs, with copy-paste curl commands for each scenario.
- Updating the golden snapshot on purpose and reviewing the diff.
- Troubleshooting a stale database, a busy port or Python older than 3.11.

**docs/AI_NOTES.md** covers the AI fluency criterion. Write it in your own voice, because reviewers will ask you to defend it.
- Which tools you used, and for what.
- Your workflow: explore the data, prototype, plan, review the plan, then build in small verified steps.
- The guardrails from section 5, and one example of each in action.
- Moments where you checked or changed what AI produced:
  - circle 17's duplicate tag;
  - circle 32's stale last_activity_at;
  - the snapshot date chosen over wall-clock time;
  - the identity rule, rejected because the requirements don't call for it;
  - post-text matching, tested and dropped because it carries no signal here;
  - the location filter, softened into a ranking factor;
  - the redundant index.
- What you kept for yourself: product judgment, weights and the final copy.

**docs/decision-log.md** records decisions made during implementation, with their evidence.

---

## 8. README and expected results

README sections:
1. What it does and why it matters, in one paragraph tied to the mission.
2. Setup, as specified in section 4.
3. API usage, with curl examples and a sample response.
4. Scenario results: one table per planted user, written by `make docs`. Each gets a line on why the result is right and the command that verifies it.
5. How it works, in a few lines, linking to DESIGN.md.
6. Verification: `make test`, `make verify` and `make fresh-check`, linking to TESTING.md.
7. Project layout, with links to SCHEMA.md, AI_NOTES.md and the decision log.

The current README's code fence uses ''' instead of backticks, so it doesn't render. Commit 13 replaces it.

These are the prototype's results. The final numbers come from the real implementation, through `make docs`.

| User | Strategy | Rank 1 | Rank 2 | Ranks 3 to 5 | Similar and excluded |
|---|---|---|---|---|---|
| 7, Seattle | personalized | #5 Women Who Lead, hybrid and led from Seattle | #6 Speak Up Circle | #40 Network & Grow, #14 Beyond Imposter Syndrome, #34 Visibility Lab | #35 and #1 are attached to #5. #38 is attached to #6. |
| 15, Chicago | personalized | #11 The Negotiation Table | #37 The Confidence Lab, virtual | #23 Allies at Work, #5 Women Who Lead, #27 Women of the 405 | #10 and #12 are attached to #11, and #13 to #37. Ranks 4 and 5 are popular picks with no interest match. |
| 23, Atlanta | personalized | #22 Level Up Collective | #2 Next Chapter Circle | #19 Working Mothers United, #16 Mentors & Sponsors, #13 Confident Voices, in person and led from Atlanta | #20 is excluded as full, and #21 as unlisted and inactive. |
| 42, empty profile | cold start | #11 The Negotiation Table | #5 Women Who Lead | #39 Mentorship Matters, #24 Burnout to Balance, #8 Managing Up Guild | All five are open and hybrid or virtual. |

Across all 100 users:

| Check | Result |
|---|---|
| Members by strategy | 70 personalized, 29 inferred, 1 cold start |
| Members whose results break a rule | 0 |
| Members with an interest signal whose rank-1 Circle matches it | 99 of 99 |
| Members shown an in-person Circle in another city | 1 |
| Ranking time per member | 0.07 ms |

---

## 9. Access and submission

You own these steps.

### A public repo

The repo is public. Reviewers can open the link without a GitHub account or an invitation, which is what the submission email asks for.

Things to know:
- **Don't add a license file.** Without one, default copyright applies: you keep all rights, and nobody may reproduce, distribute or build on the code. GitHub's terms still let other GitHub users view and fork a public repo.
- **The whole history becomes public**, including each commit's author name and email. The four existing commits use a personal Gmail address. If you'd rather not publish it, switch to your GitHub noreply address and rewrite those commits before the first push. Nothing has been pushed yet, so this is easy now and awkward later.
- **CI is free.** GitHub Actions doesn't charge for standard runners on public repos.
- **Nothing secret goes in.** The release checklist already checks for keys, .env files and circles.db.

Your noreply address is under Settings, then Emails, on GitHub. It looks like ID+USERNAME@users.noreply.github.com.

```bash
# Optional: put the noreply address on the unpushed commits. Their dates stay the same.
git config user.email "ID+USERNAME@users.noreply.github.com"
git rebase --root --exec 'git commit --amend --no-edit --author="Your Name <ID+USERNAME@users.noreply.github.com>"'

# Create the public repo and push
brew install gh && gh auth login
git branch -m master main
gh repo create leanin-circle-recommender --public --source=. --remote=origin --push
```

### Final steps

1. Run the release checklist in section 5.
2. Push main and confirm CI is green.
3. Open the repo link in a private browser window and confirm it loads without signing in.
4. Reply to the careers@sgb.org email with the link.

---

## 10. Working with AI

The assignment says: "We encourage you to use AI tools for coding and problem-solving. Show us how you work with AI, and be prepared to explain and defend the decisions reflected in your submission."

How the submission shows it:
- **A README section, "How I worked with AI".** It covers the tools, the workflow and what stayed a human decision, and links to the details.
- **docs/AI_NOTES.md.** Concrete moments where AI output was checked, changed or rejected, each with its evidence.
- **The decision log.** Calls made during implementation, with the data behind them.
- **The guardrails in section 5.** Output shown before anything counts as done, test expectations independent of the code, rules broken on purpose, and data checked before building.
- **The commit history.** AI-assisted commits carry a Co-Authored-By trailer, so the history shows where AI took part.

Decisions to be ready to defend:

| Decision | Short defense |
|---|---|
| Rules instead of ML | There's no interaction data to learn from. Rules are explainable and testable in the time. |
| Templates instead of LLM copy | Deterministic, fast and key-free, and they can't invent facts. |
| The leader's city as a location proxy, used as a multiplier | It's the only location signal, and a filter would hide valid Circles. |
| Post text not used for matching | Measured: it carries no topic signal in this dataset. |
| Bio keywords at weight 0.6 | They're the member's own words, but weaker than stated interests. |
| Topic grouping for duplicates | It matches the taxonomy, and alternatives stay visible as similar Circles. |
| Snapshot time taken from the data | The data is frozen. Wall-clock time would make every Circle look idle. |

