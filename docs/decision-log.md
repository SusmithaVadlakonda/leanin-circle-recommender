# Decision log

Decisions made while building the recommender, with the evidence behind each. [plan.md](plan.md) describes the approach. This log records the calls made along the way, including any place where the implementation departs from the plan.

| # | Decision |
|---|---|
| 1 | The minimum Python version is 3.11, not 3.10. |
| 2 | Filler results get their own explanation, separate from cold start. |
| 3 | The "most active" claim needs a high activity score. |
| 4 | Sentences without an interest match name the Circle's topic. |

---

### 1. The minimum Python version is 3.11

**Context.** The plan targeted Python 3.10 or newer.

**Evidence.** The pinned FastAPI 0.162 installs Starlette 1.9, and Starlette's package metadata requires Python 3.11 or newer. FastAPI, Uvicorn, pytest and Pydantic each require 3.10.

**Decision.** The README, the Makefile's setup check and CI all treat 3.11 as the minimum. CI tests 3.11 and 3.12.

### 2. Filler results get their own explanation

**Context.** The plan used one "popular" sentence, "One of the most active Circles right now," for two cases: cold start, and filler slots for members whose interests don't fill five results.

**Evidence.** At cold start, results are ranked mostly by activity, so the sentence is true. A filler is only the most active Circle among those that don't match the member's interests, so the claim can be false.

**Decision.** Fillers use a separate code, "explore," which reads "A change of pace from the topics in your profile." The activity sentence that follows states the facts. Cold start keeps "popular."

### 3. The "most active" claim needs a high activity score

**Context.** Cold start opens each result with "One of the most active Circles right now."

**Evidence.** The default list of five holds only very active Circles. But the API allows up to 20 results, and the later ones at cold start can be moderately active, which would make the sentence false.

**Decision.** The sentence appears only when the Circle's activity score is 0.7 or higher. Below that, the copy reads "A good place to start exploring Circles."

### 4. Sentences without an interest match name the Circle's topic

**Context.** Cold-start results and filler results have no interest to point to.

**Evidence.** Reading user 42's list as a member, all five results opened with the same sentence, so the list read like a form letter and said nothing about each Circle.

**Decision.** These sentences now end with the Circle's topic, as in "One of the most active Circles right now, focused on Negotiation." A Circle with no topic keeps the shorter sentence.
