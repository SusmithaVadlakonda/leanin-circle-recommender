# Design

## What I built

A FastAPI service backed by SQLite that returns a ranked list of Circles for a member, each with a short, member-facing explanation. It gives sensible results to every user in the dataset. 70 members are ranked from stated interests and 29 from their bio or current Circles. One member, user 42, gets a cold-start list. Ranking is pure Python over a catalog of Circle features built once at startup, and all SQL lives in one module.

## How it ranks

1. **Interest profile.** Stated interests weigh 1.0, bio keywords 0.6, and the topics of the member's own Circles 0.4. Circle topics count only when nothing is stated.
2. **Gates.** A Circle is excluded if the member is already in it, or if it's unlisted, full, or idle for 60 days. Every reason is kept for a debug view.
3. **Score.** (0.6 × relevance + 0.4 × activity) × reach. Activity is equal parts recency, posts and chat, reactions and comments per post, and the number of members posting. It gives half credit for participation when the leader writes over 80% of posts. Reach boosts an in-person Circle in the member's city and discounts one elsewhere.
4. **Diversity.** One Circle per topic. Near-duplicates fold under it as similar Circles.
5. **Explanations.** Three template sentences per result: why it fits, why it's active and how to take part.

## Signals

| Signal | Why |
|---|---|
| Stated interests, bio, current Circles | What the member has told us, strongest first. |
| Circle topic and tags | The structured content signal. |
| Access, capacity, last activity | A Circle the member can't join, or one that has gone quiet, is a broken promise. |
| 30-day posts, chat, engagement, posting members | Active means a community, not a broadcast. |
| Format and the leader's city | The member has to be able to attend. |

**Not used.** Post text carries no topic signal here: a Circle's posts match its topic no more often than chance. Job title, company and industry have nothing on the Circle side to match, and they risk stereotyping. Profile completeness and join date measure profile effort, not interests.

## Tradeoffs

- **Rules over ML.** There's no interaction data to learn from, and rules are explainable and testable in a few hours.
- **Templates over an LLM.** Deterministic, instant, free of API keys, and unable to invent facts. An Explainer interface leaves room for LLM copy generated offline.
- **Location as a multiplier, not a filter.** The leader's city is only a proxy, so a far in-person Circle sinks instead of disappearing.
- **Topic grouping for duplicates.** It's simple and keeps alternatives visible, but it would over-group a richer catalog.
- **A frozen clock.** "Now" is the data's latest timestamp, 2026-09-21. With today's date, every Circle would look idle.

## Production scale

- Compute Circle features in a scheduled job or from events, into a materialized table. Cache each member's results and invalidate them when memberships or interests change.
- Retrieve candidates with topic and geo indexes in Postgres before ranking, to cover 170,000 Circles.
- Allocate with capacity in mind, so new members aren't all sent to the same few Circles.
- Log impressions, join requests and retention. Measure success as members still active in a Circle a month later.
- Add auth, rate limits, monitoring and a versioned API path.

## With more time

- LLM-written explanations, precomputed offline and checked against the reason codes.
- Matching on post text once real posts carry topic signal, and signals from shared memberships.
- Learning to rank from join outcomes, with A/B tests.
- A real Circle location field, time zones for virtual Circles, and a "start a Circle" prompt when nothing fits.
