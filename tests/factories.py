"""Builders for unit tests: a Circle or Member with sensible defaults and any field overridden."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.recommender import Circle, Member

SNAPSHOT = datetime(2026, 9, 21, tzinfo=timezone.utc)

_BASE_CIRCLE = Circle(
    id=1,
    name="Test Circle",
    slug="test-circle",
    description=None,
    topic="negotiation",
    topic_label="Negotiation",
    tags=(),
    cover_image_url=None,
    format="virtual",
    access="public",
    join_policy="open",
    max_members=None,
    member_count=10,
    feed_posts_30d=8,
    chat_messages_30d=60,
    last_activity_at=SNAPSHOT - timedelta(days=1),
    latest_post_at=SNAPSHOT - timedelta(days=1),
    leader_city=None,
    posts_30d=8,
    authors_30d=5,
    leader_posts_30d=1,
    engagement_30d=80,
)

_BASE_MEMBER = Member(
    id=1000,
    first_name="Test",
    location=None,
    bio=None,
    topic_interests=(),
    circle_ids=frozenset(),
)


def make_circle(**overrides) -> Circle:
    if "name" in overrides and "slug" not in overrides:
        overrides["slug"] = overrides["name"].lower().replace(" ", "-")
    return replace(_BASE_CIRCLE, **overrides)


def make_member(**overrides) -> Member:
    for key in ("topic_interests",):
        if key in overrides:
            overrides[key] = tuple(overrides[key])
    if "circle_ids" in overrides:
        overrides["circle_ids"] = frozenset(overrides["circle_ids"])
    return replace(_BASE_MEMBER, **overrides)
