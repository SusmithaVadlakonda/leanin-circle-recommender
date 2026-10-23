# Data notes

Findings from `python3 scripts/inspect_data.py` over the seed files in `data/`.
The reference date for "now" is **2026-09-21**, the generator's anchor date.

## Shape

| File | Rows | Null or empty fields |
|---|---|---|
| topics.json | 22 | none |
| users.json | 100 | bio 53, company 54, location 33, job_title 24, industry 24; `topic_interests` empty for 30 users |
| circles.json | 40 | max_members 14 (uncapped), cover_image_url 6, topic 2, description 2, tags empty 2 |
| memberships.json | 441 | none |
| activity.json | 386 | none |

- **Referential integrity is clean.** Every membership and activity row points at a real user and circle, and every topic or tag is a valid topic slug.
- **`member_count` matches the membership rows** for every circle. Each circle has exactly one leader.
- **Circles 27 and 28 have no topic, no tags and no description.** They're "Women of the 405" and "The Latina Coalition", and topic matching can't reach them.
- **`last_activity_at` and the latest post can differ.** For example, circle 22 shows activity 0 days ago but its last post was 8 days ago. Treat `last_activity_at` as the overall signal, since it likely includes chat.

## Circle health

- **Circles per topic:** every topic has at least one circle. The busiest topics have 3 each: confidence, getting-promoted, leadership-skills and negotiation.
- **Unlisted (3):** circles 18 "The Only One", 21 "Career Climbers" and 30 "Early Career Collective". These shouldn't be recommended.
- **Full (1):** circle 20 "The Promotion Path" is at 15 of 15 members. It also requires a request to join.
- **Inactive, 60+ days (2):** circle 21 "Career Climbers" last had activity 227 days ago and has no posts at all. Circle 32 "The Resilience Room" last had activity 235 days ago.
- **Join policy:** 12 circles require a request to join. That's not a reason to exclude them, but it's worth saying in the explanation.

## Tags

- **Circle 17 "Hard Conversations Circle" repeats a tag.** Its tags are difficult-conversations, managing-a-team, difficult-conversations. Dedupe tags on load.
- **Tags don't reliably include the primary topic.** 28 circles repeat their topic in their tags, and 10 omit it. Match on topic and tags together.
- **Circles 10, 11 and 12 are near-duplicates.** All three are active negotiation circles, so the results need diversity.

## Planted test users

| User | Interests | Already in | Expected behavior |
|---|---|---|---|
| 7 Priya Sharma | leadership-skills, public-speaking | 4 | Easy case. Surface 5 "Women Who Lead" and 6 "Speak Up Circle", plus 1, 35 and 38. |
| 15 Nadia Haddad | negotiation, confidence | 9, 35 | Duplicate trap. Show at most one or two of circles 10, 11 and 12, and fill with confidence circles 13 or 37. Skip circle 30 because it's unlisted. |
| 23 Grace Bennett | getting-promoted | 23 | Full and inactive trap. Recommend circle 22 "Level Up Collective". Exclude 20 because it's full, and 21 because it's inactive and unlisted. |
| 42 Zoe Ellis | none | none | Cold start. The profile is empty, completeness is 0, and the user joined 2026-09-20. Fall back to active, public, non-full circles such as 1, 3, 13, 15 and 27. |

## Implications for the recommender

1. Filter out unlisted, full and inactive circles, plus circles the user already belongs to, before ranking.
2. Match on topic and tags. Dedupe tags first.
3. Add a diversity step so near-duplicate circles don't take over the list.
4. Give users with no interests a popularity and activity fallback.
5. Handle null topics, tags, descriptions and covers gracefully.
