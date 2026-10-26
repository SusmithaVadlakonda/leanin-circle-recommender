# Lean In Circle Recommender

An API that recommends the Lean In Circles a member should join, with a short, member-facing reason for each one.

Circles are small peer groups where women support each other's careers, and women in Circles are nearly twice as likely to be promoted. A recommendation only helps if the Circle is relevant, alive and open to the member. So this service never suggests a Circle that's full, inactive or unlisted. It favors Circles the member can actually attend, offers real choices instead of near-duplicates, and explains every pick in plain language.

## Quick start for reviewers

1. In a terminal, from the project folder, run `make setup` and then `make run`.
2. **Open http://127.0.0.1:8000/docs in your browser.** That page is the interactive API. The bare address, http://127.0.0.1:8000, redirects there.
3. Click **GET /users/{user_id}/recommendations**, then **Try it out**. Enter a user id such as 42, 7, 15 or 23, and click **Execute**.
4. To read results without running anything, see [the four planted scenarios](#the-four-planted-scenarios) below. Each one shows the exact request and the response it returns.

## Setup

**Prerequisites:** Python 3.11 or newer, git and make. macOS developer tools and most Linux distributions include make. On Windows, use WSL or the commands under "Without make".

```bash
git clone <repo-url>
cd leanin-circle-recommender
make setup
make run
```

`make run` serves the API on port 8000. **Open the interactive docs at http://127.0.0.1:8000/docs.** The first start builds `circles.db` from `data/`, and `make help` lists every target.

In a second terminal:

```bash
curl -s http://127.0.0.1:8000/users/7/recommendations
make test
```

User 7's first recommendation should be Women Who Lead.

### Without make

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --port 8000
.venv/bin/python -m pytest
```

On native Windows, use `.venv\Scripts\python` wherever these commands say `.venv/bin/python`.

### Troubleshooting

- **Python is too old.** `make setup` stops and prints the version it found. Install 3.11 or newer, then run `make setup PYTHON=python3.12`.
- **Port 8000 is busy.** Run `make run PORT=8001`.
- **The database looks stale.** Run `make seed` to rebuild it from `data/`, then restart the server.

## API

`GET /users/{user_id}/recommendations`

| Parameter | Default | Meaning |
|---|---|---|
| `limit` | 5 | How many Circles to return, from 1 to 20. |
| `include_excluded` | false | Debug view: also list the Circles that were left out, with every reason. |

An unknown user returns 404, and an invalid limit or user id returns 422. `GET /health` returns `{"status": "ok"}`, and `GET /` redirects to the docs page.

```bash
curl -s "http://127.0.0.1:8000/users/23/recommendations?limit=1&include_excluded=true"
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
        "id": 22, "name": "Level Up Collective", "slug": "level-up-collective",
        "description": "A supportive circle for women focused on getting promoted.",
        "topic": "getting-promoted", "topic_label": "Getting promoted",
        "format": "hybrid", "join_policy": "request",
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
    {"circle_id": 21, "name": "Career Climbers", "reasons": ["unlisted", "inactive"]},
    "..."
  ]
}
```

- **strategy** is `personalized` for stated interests, `inferred` when only the bio or current Circles say anything, and `cold_start` when nothing does.
- **profile_nudge** asks members without stated interests to add some.
- **score** is for debugging and tuning, not for display.
- **similar_circles** lists the near-duplicates folded under a result.

## How it works

1. **Interest profile.** Stated interests weigh 1.0, bio keywords 0.6, and the topics of Circles the member is already in 0.4. Circle topics count only when nothing is stated.
2. **Gates.** Circles the member is in, unlisted ones, full ones and ones idle for 60 days are left out.
3. **Score.** Relevance and activity, multiplied by reach. Activity counts recency, posts and chat, reactions and comments per post, and how many different members post. Reach uses the leader's city as the Circle's location.
4. **Diversity.** One Circle per topic. Near-duplicates fold under it as similar Circles.
5. **Explanations.** Three template sentences: why it fits, why it's active and how to take part.

[docs/DESIGN.md](docs/DESIGN.md) is the one-page design, with the tradeoffs and the path to production. [docs/SCHEMA.md](docs/SCHEMA.md) covers the tables and indexes.

## The four planted scenarios

The dataset README plants four users to test the recommender. For each one, this section shows the request, the response it returns and why the result is right. `make docs` generates the section by calling the API, and `make verify` fails if it no longer matches, so what you read here is what the code returns.

<!-- scenarios:start -->
### User 42: Cold start

**What's planted.** No memberships, no stated interests and an empty profile.

**Profile.** No stated interests. No location. No bio.

**Input**

```bash
curl -s "http://127.0.0.1:8000/users/42/recommendations"
```

**Output**

Strategy: `cold_start`. Nudge: "Add a few interests to your profile and we'll tailor these picks to you."

| Rank | Circle | Why it's recommended | Similar Circles |
|---|---|---|---|
| 1 | #11 The Negotiation Table | One of the most active Circles right now, focused on Negotiation. 8 members posted in the last 30 days. Hybrid, so you can join online. | #10 Negotiation Circle, #12 Negotiate Like a Leader |
| 2 | #5 Women Who Lead | One of the most active Circles right now, focused on Leadership skills. 8 members posted in the last 30 days. Hybrid, so you can join online. | #1 The Elevation Circle, #35 Board-Ready Women |
| 3 | #39 Mentorship Matters | One of the most active Circles right now, focused on Sponsorship & mentorship. 7 members posted in the last 30 days. Meets virtually, so you can join from anywhere. | #16 Mentors & Sponsors |
| 4 | #24 Burnout to Balance | One of the most active Circles right now, focused on Stress & burnout. 7 members posted in the last 30 days. Hybrid, so you can join online. | none |
| 5 | #8 Managing Up Guild | One of the most active Circles right now, focused on Managing up. 8 posts in the last 30 days. Hybrid, so you can join online. | none |

**Why this is right.** There's nothing to personalize on, so the list holds the most active open Circles, each on a different topic. All five are hybrid or virtual, because the member's location is unknown. The response asks the member to add interests.

<details>
<summary>Full JSON response for user 42</summary>

```json
{
  "user_id": 42,
  "as_of": "2026-09-21T00:00:00Z",
  "strategy": "cold_start",
  "profile_nudge": "Add a few interests to your profile and we'll tailor these picks to you.",
  "explanation_source": "template",
  "recommendations": [
    {
      "rank": 1,
      "score": 1.0,
      "circle": {
        "id": 11,
        "name": "The Negotiation Table",
        "slug": "the-negotiation-table",
        "description": "A supportive circle for women focused on negotiation.",
        "topic": "negotiation",
        "topic_label": "Negotiation",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 15,
        "max_members": 25,
        "spots_left": 10,
        "cover_image_url": "https://images.example.org/circles/the-negotiation-table.jpg"
      },
      "explanation": "One of the most active Circles right now, focused on Negotiation. 8 members posted in the last 30 days. Hybrid, so you can join online.",
      "reasons": [
        {
          "code": "popular",
          "text": "One of the most active Circles right now, focused on Negotiation."
        },
        {"code": "members_posting", "text": "8 members posted in the last 30 days."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": [
        {"id": 10, "name": "Negotiation Circle", "format": "in_person"},
        {"id": 12, "name": "Negotiate Like a Leader", "format": "in_person"}
      ]
    },
    {
      "rank": 2,
      "score": 0.944,
      "circle": {
        "id": 5,
        "name": "Women Who Lead",
        "slug": "women-who-lead",
        "description": "A supportive circle for women focused on leadership skills.",
        "topic": "leadership-skills",
        "topic_label": "Leadership skills",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 24,
        "max_members": 31,
        "spots_left": 7,
        "cover_image_url": "https://images.example.org/circles/women-who-lead.jpg"
      },
      "explanation": "One of the most active Circles right now, focused on Leadership skills. 8 members posted in the last 30 days. Hybrid, so you can join online.",
      "reasons": [
        {
          "code": "popular",
          "text": "One of the most active Circles right now, focused on Leadership skills."
        },
        {"code": "members_posting", "text": "8 members posted in the last 30 days."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": [
        {"id": 1, "name": "The Elevation Circle", "format": "in_person"},
        {"id": 35, "name": "Board-Ready Women", "format": "in_person"}
      ]
    },
    {
      "rank": 3,
      "score": 0.923,
      "circle": {
        "id": 39,
        "name": "Mentorship Matters",
        "slug": "mentorship-matters",
        "description": "A supportive circle for women focused on sponsorship & mentorship.",
        "topic": "sponsorship-mentorship",
        "topic_label": "Sponsorship & mentorship",
        "format": "virtual",
        "join_policy": "open",
        "member_count": 11,
        "max_members": 17,
        "spots_left": 6,
        "cover_image_url": null
      },
      "explanation": "One of the most active Circles right now, focused on Sponsorship & mentorship. 7 members posted in the last 30 days. Meets virtually, so you can join from anywhere.",
      "reasons": [
        {
          "code": "popular",
          "text": "One of the most active Circles right now, focused on Sponsorship & mentorship."
        },
        {"code": "members_posting", "text": "7 members posted in the last 30 days."},
        {"code": "virtual", "text": "Meets virtually, so you can join from anywhere."}
      ],
      "similar_circles": [{"id": 16, "name": "Mentors & Sponsors", "format": "virtual"}]
    },
    {
      "rank": 4,
      "score": 0.887,
      "circle": {
        "id": 24,
        "name": "Burnout to Balance",
        "slug": "burnout-to-balance",
        "description": "A supportive circle for women focused on stress & burnout.",
        "topic": "stress-burnout",
        "topic_label": "Stress & burnout",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 10,
        "max_members": 16,
        "spots_left": 6,
        "cover_image_url": "https://images.example.org/circles/burnout-to-balance.jpg"
      },
      "explanation": "One of the most active Circles right now, focused on Stress & burnout. 7 members posted in the last 30 days. Hybrid, so you can join online.",
      "reasons": [
        {
          "code": "popular",
          "text": "One of the most active Circles right now, focused on Stress & burnout."
        },
        {"code": "members_posting", "text": "7 members posted in the last 30 days."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": []
    },
    {
      "rank": 5,
      "score": 0.798,
      "circle": {
        "id": 8,
        "name": "Managing Up Guild",
        "slug": "managing-up-guild",
        "description": "A supportive circle for women focused on managing up.",
        "topic": "managing-up",
        "topic_label": "Managing up",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 15,
        "max_members": null,
        "spots_left": null,
        "cover_image_url": "https://images.example.org/circles/managing-up-guild.jpg"
      },
      "explanation": "One of the most active Circles right now, focused on Managing up. 8 posts in the last 30 days. Hybrid, so you can join online.",
      "reasons": [
        {
          "code": "popular",
          "text": "One of the most active Circles right now, focused on Managing up."
        },
        {"code": "busy", "text": "8 posts in the last 30 days."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": []
    }
  ],
  "excluded": null
}
```

</details>

### User 7: Obvious matches

**What's planted.** Interested in leadership skills and public speaking, with strong active Circles for both: #5 Women Who Lead and #6 Speak Up Circle.

**Profile.** Stated interests: Leadership skills, Public speaking. Location: Seattle, WA. Bio: "Senior IC eyeing my first leadership role. Working on executive presence."

**Input**

```bash
curl -s "http://127.0.0.1:8000/users/7/recommendations"
```

**Output**

Strategy: `personalized`.

| Rank | Circle | Why it's recommended | Similar Circles |
|---|---|---|---|
| 1 | #5 Women Who Lead | Focused on Leadership skills, one of your interests. 8 members posted in the last 30 days. Led from Seattle, WA, close to you. | #35 Board-Ready Women, #1 The Elevation Circle |
| 2 | #6 Speak Up Circle | Covers Public speaking and Leadership skills, both on your list. 5 members posted in the last 30 days. Meets in person. | #38 Speak With Impact |
| 3 | #40 Network & Grow | Also covers Leadership skills, one of your interests. Active this week. Hybrid, so you can join online. | #15 The Network Effect |
| 4 | #14 Beyond Imposter Syndrome | Also covers Public speaking, one of your interests. Active in the last month. Hybrid, so you can join online. | none |
| 5 | #34 Visibility Lab | Also covers Public speaking, one of your interests. Active this week. Hybrid, so you can join online. | #9 Seen & Heard |

**Why this is right.** Women Who Lead and Speak Up Circle take the first two places, as the dataset README expects.

<details>
<summary>Full JSON response for user 7</summary>

```json
{
  "user_id": 7,
  "as_of": "2026-09-21T00:00:00Z",
  "strategy": "personalized",
  "profile_nudge": null,
  "explanation_source": "template",
  "recommendations": [
    {
      "rank": 1,
      "score": 1.071,
      "circle": {
        "id": 5,
        "name": "Women Who Lead",
        "slug": "women-who-lead",
        "description": "A supportive circle for women focused on leadership skills.",
        "topic": "leadership-skills",
        "topic_label": "Leadership skills",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 24,
        "max_members": 31,
        "spots_left": 7,
        "cover_image_url": "https://images.example.org/circles/women-who-lead.jpg"
      },
      "explanation": "Focused on Leadership skills, one of your interests. 8 members posted in the last 30 days. Led from Seattle, WA, close to you.",
      "reasons": [
        {"code": "interest_topic", "text": "Focused on Leadership skills, one of your interests."},
        {"code": "members_posting", "text": "8 members posted in the last 30 days."},
        {"code": "near_you", "text": "Led from Seattle, WA, close to you."}
      ],
      "similar_circles": [
        {"id": 35, "name": "Board-Ready Women", "format": "in_person"},
        {"id": 1, "name": "The Elevation Circle", "format": "in_person"}
      ]
    },
    {
      "rank": 2,
      "score": 0.734,
      "circle": {
        "id": 6,
        "name": "Speak Up Circle",
        "slug": "speak-up-circle",
        "description": "A supportive circle for women focused on public speaking.",
        "topic": "public-speaking",
        "topic_label": "Public speaking",
        "format": "in_person",
        "join_policy": "open",
        "member_count": 9,
        "max_members": 13,
        "spots_left": 4,
        "cover_image_url": "https://images.example.org/circles/speak-up-circle.jpg"
      },
      "explanation": "Covers Public speaking and Leadership skills, both on your list. 5 members posted in the last 30 days. Meets in person.",
      "reasons": [
        {
          "code": "interest_multi",
          "text": "Covers Public speaking and Leadership skills, both on your list."
        },
        {"code": "members_posting", "text": "5 members posted in the last 30 days."},
        {"code": "in_person", "text": "Meets in person."}
      ],
      "similar_circles": [{"id": 38, "name": "Speak With Impact", "format": "in_person"}]
    },
    {
      "rank": 3,
      "score": 0.479,
      "circle": {
        "id": 40,
        "name": "Network & Grow",
        "slug": "network-and-grow",
        "description": "A supportive circle for women focused on networking.",
        "topic": "networking",
        "topic_label": "Networking",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 12,
        "max_members": null,
        "spots_left": null,
        "cover_image_url": "https://images.example.org/circles/network-and-grow.jpg"
      },
      "explanation": "Also covers Leadership skills, one of your interests. Active this week. Hybrid, so you can join online.",
      "reasons": [
        {"code": "interest_tag", "text": "Also covers Leadership skills, one of your interests."},
        {"code": "active_week", "text": "Active this week."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": [{"id": 15, "name": "The Network Effect", "format": "in_person"}]
    },
    {
      "rank": 4,
      "score": 0.472,
      "circle": {
        "id": 14,
        "name": "Beyond Imposter Syndrome",
        "slug": "beyond-imposter-syndrome",
        "description": "A supportive circle for women focused on imposter syndrome.",
        "topic": "imposter-syndrome",
        "topic_label": "Imposter syndrome",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 6,
        "max_members": 10,
        "spots_left": 4,
        "cover_image_url": "https://images.example.org/circles/beyond-imposter-syndrome.jpg"
      },
      "explanation": "Also covers Public speaking, one of your interests. Active in the last month. Hybrid, so you can join online.",
      "reasons": [
        {"code": "interest_tag", "text": "Also covers Public speaking, one of your interests."},
        {"code": "active_month", "text": "Active in the last month."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": []
    },
    {
      "rank": 5,
      "score": 0.44,
      "circle": {
        "id": 34,
        "name": "Visibility Lab",
        "slug": "visibility-lab",
        "description": "A supportive circle for women focused on visibility & recognition.",
        "topic": "visibility-recognition",
        "topic_label": "Visibility & recognition",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 7,
        "max_members": 10,
        "spots_left": 3,
        "cover_image_url": "https://images.example.org/circles/visibility-lab.jpg"
      },
      "explanation": "Also covers Public speaking, one of your interests. Active this week. Hybrid, so you can join online.",
      "reasons": [
        {"code": "interest_tag", "text": "Also covers Public speaking, one of your interests."},
        {"code": "active_week", "text": "Active this week."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": [{"id": 9, "name": "Seen & Heard", "format": "virtual"}]
    }
  ],
  "excluded": null
}
```

</details>

### User 15: Duplicate Circles

**What's planted.** Interested in negotiation, where #10, #11 and #12 are three near-identical active Circles.

**Profile.** Stated interests: Negotiation, Confidence. Location: Chicago, IL. Bio: "Prepping for a big comp conversation and want to build confidence around it."

**Input**

```bash
curl -s "http://127.0.0.1:8000/users/15/recommendations"
```

**Output**

Strategy: `personalized`.

| Rank | Circle | Why it's recommended | Similar Circles |
|---|---|---|---|
| 1 | #11 The Negotiation Table | Focused on Negotiation, one of your interests. 8 members posted in the last 30 days. Hybrid, so you can join online. | #10 Negotiation Circle, #12 Negotiate Like a Leader |
| 2 | #37 The Confidence Lab | Focused on Confidence, one of your interests. Active this week. Request to join; the leader approves new members. | #13 Confident Voices |
| 3 | #23 Allies at Work | Also covers Negotiation, one of your interests. Active this week. Meets virtually, so you can join from anywhere. | none |
| 4 | #5 Women Who Lead | A change of pace from your profile's topics, focused on Leadership skills. 8 members posted in the last 30 days. Hybrid, so you can join online. | #1 The Elevation Circle |
| 5 | #27 Women of the 405 | A change of pace from the topics in your profile. 9 members posted in the last 30 days. Request to join; the leader approves new members. | none |

**Why this is right.** Only one negotiation Circle takes a slot. The other two are attached to it as similar Circles, so the member still sees them without losing three of five places to one topic.

<details>
<summary>Full JSON response for user 15</summary>

```json
{
  "user_id": 15,
  "as_of": "2026-09-21T00:00:00Z",
  "strategy": "personalized",
  "profile_nudge": null,
  "explanation_source": "template",
  "recommendations": [
    {
      "rank": 1,
      "score": 1.0,
      "circle": {
        "id": 11,
        "name": "The Negotiation Table",
        "slug": "the-negotiation-table",
        "description": "A supportive circle for women focused on negotiation.",
        "topic": "negotiation",
        "topic_label": "Negotiation",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 15,
        "max_members": 25,
        "spots_left": 10,
        "cover_image_url": "https://images.example.org/circles/the-negotiation-table.jpg"
      },
      "explanation": "Focused on Negotiation, one of your interests. 8 members posted in the last 30 days. Hybrid, so you can join online.",
      "reasons": [
        {"code": "interest_topic", "text": "Focused on Negotiation, one of your interests."},
        {"code": "members_posting", "text": "8 members posted in the last 30 days."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": [
        {"id": 10, "name": "Negotiation Circle", "format": "in_person"},
        {"id": 12, "name": "Negotiate Like a Leader", "format": "in_person"}
      ]
    },
    {
      "rank": 2,
      "score": 0.807,
      "circle": {
        "id": 37,
        "name": "The Confidence Lab",
        "slug": "the-confidence-lab",
        "description": "A supportive circle for women focused on confidence.",
        "topic": "confidence",
        "topic_label": "Confidence",
        "format": "virtual",
        "join_policy": "request",
        "member_count": 8,
        "max_members": null,
        "spots_left": null,
        "cover_image_url": "https://images.example.org/circles/the-confidence-lab.jpg"
      },
      "explanation": "Focused on Confidence, one of your interests. Active this week. Request to join; the leader approves new members.",
      "reasons": [
        {"code": "interest_topic", "text": "Focused on Confidence, one of your interests."},
        {"code": "active_week", "text": "Active this week."},
        {"code": "request_to_join", "text": "Request to join; the leader approves new members."}
      ],
      "similar_circles": [{"id": 13, "name": "Confident Voices", "format": "in_person"}]
    },
    {
      "rank": 3,
      "score": 0.494,
      "circle": {
        "id": 23,
        "name": "Allies at Work",
        "slug": "allies-at-work",
        "description": "A supportive circle for women focused on allyship.",
        "topic": "allyship",
        "topic_label": "Allyship",
        "format": "virtual",
        "join_policy": "open",
        "member_count": 11,
        "max_members": 20,
        "spots_left": 9,
        "cover_image_url": "https://images.example.org/circles/allies-at-work.jpg"
      },
      "explanation": "Also covers Negotiation, one of your interests. Active this week. Meets virtually, so you can join from anywhere.",
      "reasons": [
        {"code": "interest_tag", "text": "Also covers Negotiation, one of your interests."},
        {"code": "active_week", "text": "Active this week."},
        {"code": "virtual", "text": "Meets virtually, so you can join from anywhere."}
      ],
      "similar_circles": []
    },
    {
      "rank": 4,
      "score": 0.374,
      "circle": {
        "id": 5,
        "name": "Women Who Lead",
        "slug": "women-who-lead",
        "description": "A supportive circle for women focused on leadership skills.",
        "topic": "leadership-skills",
        "topic_label": "Leadership skills",
        "format": "hybrid",
        "join_policy": "open",
        "member_count": 24,
        "max_members": 31,
        "spots_left": 7,
        "cover_image_url": "https://images.example.org/circles/women-who-lead.jpg"
      },
      "explanation": "A change of pace from your profile's topics, focused on Leadership skills. 8 members posted in the last 30 days. Hybrid, so you can join online.",
      "reasons": [
        {
          "code": "explore",
          "text": "A change of pace from your profile's topics, focused on Leadership skills."
        },
        {"code": "members_posting", "text": "8 members posted in the last 30 days."},
        {"code": "hybrid", "text": "Hybrid, so you can join online."}
      ],
      "similar_circles": [{"id": 1, "name": "The Elevation Circle", "format": "in_person"}]
    },
    {
      "rank": 5,
      "score": 0.366,
      "circle": {
        "id": 27,
        "name": "Women of the 405",
        "slug": "women-of-the-405",
        "description": null,
        "topic": null,
        "topic_label": null,
        "format": "virtual",
        "join_policy": "request",
        "member_count": 12,
        "max_members": 22,
        "spots_left": 10,
        "cover_image_url": "https://images.example.org/circles/women-of-the-405.jpg"
      },
      "explanation": "A change of pace from the topics in your profile. 9 members posted in the last 30 days. Request to join; the leader approves new members.",
      "reasons": [
        {"code": "explore", "text": "A change of pace from the topics in your profile."},
        {"code": "members_posting", "text": "9 members posted in the last 30 days."},
        {"code": "request_to_join", "text": "Request to join; the leader approves new members."}
      ],
      "similar_circles": []
    }
  ],
  "excluded": null
}
```

</details>

### User 23: Full or inactive Circles

**What's planted.** Interested in getting promoted. #20 The Promotion Path is full and #21 Career Climbers is inactive, while #22 Level Up Collective is healthy.

**Profile.** Stated interests: Getting promoted. Location: Atlanta, GA. Bio: "Been in-role two years and ready for the next level."

**Input**

```bash
curl -s "http://127.0.0.1:8000/users/23/recommendations?include_excluded=true"
```

**Output**

Strategy: `personalized`.

| Rank | Circle | Why it's recommended | Similar Circles |
|---|---|---|---|
| 1 | #22 Level Up Collective | Focused on Getting promoted, one of your interests. 5 members posted in the last 30 days. Request to join; the leader approves new members. | none |
| 2 | #2 Next Chapter Circle | Also covers Getting promoted, one of your interests. 5 members posted in the last 30 days. Meets virtually, so you can join from anywhere. | #33 Return & Rise |
| 3 | #19 Working Mothers United | Also covers Getting promoted, one of your interests. 7 members posted in the last 30 days. Request to join; the leader approves new members. | #29 Professionals Who Parent |
| 4 | #16 Mentors & Sponsors | Also covers Getting promoted, one of your interests. Active in the last month. Meets virtually, so you can join from anywhere. | #39 Mentorship Matters |
| 5 | #13 Confident Voices | A change of pace from your profile's topics, focused on Confidence. 9 members posted in the last 30 days. Led from Atlanta, GA, close to you. | #37 The Confidence Lab |

Left out, from the response's excluded list:

- #18 The Only One: unlisted
- #20 The Promotion Path: full
- #21 Career Climbers: unlisted, inactive
- #23 Allies at Work: already a member
- #30 Early Career Collective: unlisted
- #32 The Resilience Room: inactive

**Why this is right.** Level Up Collective leads. The Promotion Path and Career Climbers appear nowhere, not even as similar Circles. The request turns on include_excluded, so the response lists them with the reasons.

<details>
<summary>Full JSON response for user 23</summary>

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
        "id": 22,
        "name": "Level Up Collective",
        "slug": "level-up-collective",
        "description": "A supportive circle for women focused on getting promoted.",
        "topic": "getting-promoted",
        "topic_label": "Getting promoted",
        "format": "hybrid",
        "join_policy": "request",
        "member_count": 14,
        "max_members": 20,
        "spots_left": 6,
        "cover_image_url": "https://images.example.org/circles/level-up-collective.jpg"
      },
      "explanation": "Focused on Getting promoted, one of your interests. 5 members posted in the last 30 days. Request to join; the leader approves new members.",
      "reasons": [
        {"code": "interest_topic", "text": "Focused on Getting promoted, one of your interests."},
        {"code": "members_posting", "text": "5 members posted in the last 30 days."},
        {"code": "request_to_join", "text": "Request to join; the leader approves new members."}
      ],
      "similar_circles": []
    },
    {
      "rank": 2,
      "score": 0.526,
      "circle": {
        "id": 2,
        "name": "Next Chapter Circle",
        "slug": "next-chapter-circle",
        "description": "A supportive circle for women focused on career breaks.",
        "topic": "career-breaks",
        "topic_label": "Career breaks",
        "format": "virtual",
        "join_policy": "open",
        "member_count": 14,
        "max_members": null,
        "spots_left": null,
        "cover_image_url": "https://images.example.org/circles/next-chapter-circle.jpg"
      },
      "explanation": "Also covers Getting promoted, one of your interests. 5 members posted in the last 30 days. Meets virtually, so you can join from anywhere.",
      "reasons": [
        {"code": "interest_tag", "text": "Also covers Getting promoted, one of your interests."},
        {"code": "members_posting", "text": "5 members posted in the last 30 days."},
        {"code": "virtual", "text": "Meets virtually, so you can join from anywhere."}
      ],
      "similar_circles": [{"id": 33, "name": "Return & Rise", "format": "hybrid"}]
    },
    {
      "rank": 3,
      "score": 0.51,
      "circle": {
        "id": 19,
        "name": "Working Mothers United",
        "slug": "working-mothers-united",
        "description": "A supportive circle for women focused on working motherhood.",
        "topic": "working-motherhood",
        "topic_label": "Working motherhood",
        "format": "in_person",
        "join_policy": "request",
        "member_count": 10,
        "max_members": null,
        "spots_left": null,
        "cover_image_url": "https://images.example.org/circles/working-mothers-united.jpg"
      },
      "explanation": "Also covers Getting promoted, one of your interests. 7 members posted in the last 30 days. Request to join; the leader approves new members.",
      "reasons": [
        {"code": "interest_tag", "text": "Also covers Getting promoted, one of your interests."},
        {"code": "members_posting", "text": "7 members posted in the last 30 days."},
        {"code": "request_to_join", "text": "Request to join; the leader approves new members."}
      ],
      "similar_circles": [{"id": 29, "name": "Professionals Who Parent", "format": "in_person"}]
    },
    {
      "rank": 4,
      "score": 0.487,
      "circle": {
        "id": 16,
        "name": "Mentors & Sponsors",
        "slug": "mentors-and-sponsors",
        "description": "A supportive circle for women focused on sponsorship & mentorship.",
        "topic": "sponsorship-mentorship",
        "topic_label": "Sponsorship & mentorship",
        "format": "virtual",
        "join_policy": "open",
        "member_count": 12,
        "max_members": null,
        "spots_left": null,
        "cover_image_url": null
      },
      "explanation": "Also covers Getting promoted, one of your interests. Active in the last month. Meets virtually, so you can join from anywhere.",
      "reasons": [
        {"code": "interest_tag", "text": "Also covers Getting promoted, one of your interests."},
        {"code": "active_month", "text": "Active in the last month."},
        {"code": "virtual", "text": "Meets virtually, so you can join from anywhere."}
      ],
      "similar_circles": [{"id": 39, "name": "Mentorship Matters", "format": "virtual"}]
    },
    {
      "rank": 5,
      "score": 0.423,
      "circle": {
        "id": 13,
        "name": "Confident Voices",
        "slug": "confident-voices",
        "description": "A supportive circle for women focused on confidence.",
        "topic": "confidence",
        "topic_label": "Confidence",
        "format": "in_person",
        "join_policy": "open",
        "member_count": 12,
        "max_members": 18,
        "spots_left": 6,
        "cover_image_url": "https://images.example.org/circles/confident-voices.jpg"
      },
      "explanation": "A change of pace from your profile's topics, focused on Confidence. 9 members posted in the last 30 days. Led from Atlanta, GA, close to you.",
      "reasons": [
        {
          "code": "explore",
          "text": "A change of pace from your profile's topics, focused on Confidence."
        },
        {"code": "members_posting", "text": "9 members posted in the last 30 days."},
        {"code": "near_you", "text": "Led from Atlanta, GA, close to you."}
      ],
      "similar_circles": [{"id": 37, "name": "The Confidence Lab", "format": "virtual"}]
    }
  ],
  "excluded": [
    {"circle_id": 18, "name": "The Only One", "reasons": ["unlisted"]},
    {"circle_id": 20, "name": "The Promotion Path", "reasons": ["full"]},
    {"circle_id": 21, "name": "Career Climbers", "reasons": ["unlisted", "inactive"]},
    {"circle_id": 23, "name": "Allies at Work", "reasons": ["already_member"]},
    {"circle_id": 30, "name": "Early Career Collective", "reasons": ["unlisted"]},
    {"circle_id": 32, "name": "The Resilience Room", "reasons": ["inactive"]}
  ]
}
```

</details>
<!-- scenarios:end -->

## Verification

```bash
make test         # unit, API, scenario and invariant tests
make verify       # the tests, a live smoke test against the real server, the benchmark and the README check
make fresh-check  # clone the committed repo and follow this README from scratch
```

CI runs `make setup` and `make verify` on Python 3.11 and 3.12 for every push. Latency is measured in process across all 100 users. In the last run, p95 was 2.4 ms over 500 requests, against a 50 ms target. [docs/TESTING.md](docs/TESTING.md) explains each check.

## How I worked with AI

> "We encourage you to use AI tools for coding and problem-solving. Show us how you work with AI, and be prepared to explain and defend the decisions reflected in your submission."

I built this with Claude Code, Anthropic's coding agent, from first data exploration to the final docs. The working pattern was the same throughout:
- **The AI proposed and gathered evidence.** It drafted the plan, prototyped the ranking against all 100 users, and measured signals before we relied on them.
- **I reviewed and decided.** I changed the plan in several places. Location became a ranking factor instead of a filter. Activity now counts how many members post, not just volume. Bios became an interest source. A proposed rule about identity-based Circles was dropped.
- **Nothing counted without proof.** Tests come from the plan and the dataset README, not from the code. Each key rule was broken on purpose to confirm a test catches it. AI-assisted commits carry a `Co-Authored-By` trailer.

[docs/AI_NOTES.md](docs/AI_NOTES.md) lists the specific moments where AI output was checked, changed or rejected. [docs/decision-log.md](docs/decision-log.md) records the decisions made during the build, and [docs/plan.md](docs/plan.md) is the plan the work followed.

## Project layout

```
app/
  main.py          FastAPI app and routes; seeds a missing database at startup
  schemas.py       response models, which define the JSON contract
  config.py        settings from environment variables
  recommender.py   interest profile, gates, scoring, diversity and cold start; pure Python
  explain.py       reason codes, templates and the explainer interface
  service.py       loads the recommender and members from the database
  models.py        all SQL
  seed.py          JSON to SQLite
  schema.sql       tables and indexes
  timestamps.py    the data's timestamp format
scripts/           scenarios, smoke test, benchmark, fresh-clone check, data inspection
tests/             unit, API, scenario and invariant tests, plus the golden snapshot
docs/              design, schema, testing, AI notes, decision log, plan and dataset notes
data/              the seed dataset
```
