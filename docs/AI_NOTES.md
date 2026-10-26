# Working with AI

The assignment asks: "We encourage you to use AI tools for coding and problem-solving. Show us how you work with AI, and be prepared to explain and defend the decisions reflected in your submission." This is how I did it.

## Tools

I used Claude Code, Anthropic's coding agent, in VS Code for the whole project. It read the data, drafted the plan, wrote code, tests and docs, and ran every check. Commits it helped write carry a `Co-Authored-By` trailer, so the history shows where AI took part.

## How I worked

1. **Data first.** An inspection script, [scripts/inspect_data.py](../scripts/inspect_data.py), and the [dataset notes](data-notes.md) came before any design.
2. **Prototype before planning.** Throwaway prototypes ranked all 100 users against the planted scenarios before the plan committed to an approach.
3. **Plan, then review.** The AI drafted [plan.md](plan.md) from the requirements. I reviewed it point by point and changed it, as listed below.
4. **Small, verified steps.** One commit per piece, with tests written from the plan and the verification loop run before every commit.

## Guardrails

- **Show the output.** Nothing counted as done until its test output was on screen.
- **Independent expectations.** Scenario tests come from the dataset README. Data-layer tests recompute every number from the raw JSON instead of trusting the code under test.
- **Break it on purpose.** Each key rule was disabled once to confirm the right tests fail. [TESTING.md](TESTING.md) has the results.
- **Data before heuristics.** Every new signal was measured against the data before it was built.

## Where I changed course

| AI proposal | What I decided | Why |
|---|---|---|
| Show identity-based Circles, such as working mothers, only to members who chose that topic | Dropped the rule | The requirements don't ask for it, so every topic is treated the same. |
| Exclude in-person Circles led from another city | Location became a ranking multiplier | The leader's city is only a proxy for where a Circle meets. |
| Measure activity by post and chat volume | Added engagement and the number of members posting | A Circle is active when its community is, not just its leader. |
| Leave bios unused | Bio keywords became a weaker interest source | 12 members with no stated interests now get personal picks. |
| Feature-branch pull requests | Commit straight to main | I'm the only developer. |
| A Makefile as a nice-to-have | The Makefile and setup instructions became deliverables, checked by CI and a fresh-clone test | Reviewers have to be able to run it. |

I also suggested matching topics from post text in activity.json. The AI measured it first: a Circle's posts match its own topic no more often than chance. We dropped it and used activity.json for engagement and participation instead.

## What the AI caught

- Circle 17 lists one tag twice, which broke a plain insert into the tags table.
- Circle 32's newest post is newer than its `last_activity_at`, so idle time uses the later of the two.
- The data is frozen on 2026-09-21. Using today's date would have made every Circle look idle.
- An index on `memberships(user_id)` duplicated the primary key's index.
- The pinned FastAPI installs Starlette 1.9, which needs Python 3.11, so the minimum moved up from 3.10.
- One of its own tests was wrong. It asked for five results from three topics, and the backfill rule correctly filled the list. The test was fixed, not the code.
- Reading user 42's results as a member, all five opened with the same sentence. The copy now names each Circle's topic.
- Breaking the full gate on purpose exposed a weak test. A full Circle could still have been offered as a "similar Circle" without any test failing. The scenario and invariant tests now check similar Circles too.

## What I kept for myself

Product judgment about what members need, and sign-off on the scoring weights, the copy and every entry in the [decision log](decision-log.md). The AI proposed options and gathered evidence. The data and I decided.
