"""Ranking logic: interest profile, eligibility gates, scoring, diversity and cold start.

Pure Python. Everything arrives as plain data from app.models, so this module never
touches the database and its unit tests need none.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime

from app.timestamps import parse_timestamp

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

_NOT_A_CITY = {"remote"}


def city_of(location: str | None) -> str | None:
    """A location usable for in-person matching, or None when missing or "Remote"."""
    if not location or location.strip().lower() in _NOT_A_CITY:
        return None
    return location.strip()


@dataclass(frozen=True)
class Circle:
    """One Circle with the features ranking needs. Built from a catalog row."""

    id: int
    name: str
    slug: str
    description: str | None
    topic: str | None
    topic_label: str | None
    tags: tuple[str, ...]
    cover_image_url: str | None
    format: str
    access: str
    join_policy: str
    max_members: int | None
    member_count: int
    feed_posts_30d: int
    chat_messages_30d: int
    last_activity_at: datetime | None
    latest_post_at: datetime | None
    leader_city: str | None
    posts_30d: int
    authors_30d: int
    leader_posts_30d: int
    engagement_30d: int

    @classmethod
    def from_row(cls, row: dict) -> Circle:
        return cls(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            description=row["description"],
            topic=row["topic"],
            topic_label=row["topic_label"],
            tags=tuple(row["tags"]),
            cover_image_url=row["cover_image_url"],
            format=row["format"],
            access=row["access"],
            join_policy=row["join_policy"],
            max_members=row["max_members"],
            member_count=row["member_count"],
            feed_posts_30d=row["feed_posts_30d"],
            chat_messages_30d=row["chat_messages_30d"],
            last_activity_at=_maybe_timestamp(row["last_activity_at"]),
            latest_post_at=_maybe_timestamp(row["latest_post_at"]),
            leader_city=city_of(row["leader_location"]),
            posts_30d=row["posts_30d"],
            authors_30d=row["authors_30d"],
            leader_posts_30d=row["leader_posts_30d"],
            engagement_30d=row["engagement_30d"],
        )

    @property
    def is_full(self) -> bool:
        return self.max_members is not None and self.member_count >= self.max_members

    @property
    def spots_left(self) -> int | None:
        """Open seats, or None when the Circle is uncapped."""
        if self.max_members is None:
            return None
        return max(0, self.max_members - self.member_count)

    def idle_days(self, as_of: datetime) -> float:
        """Days since the last sign of life: the later of last_activity_at and the newest post.

        Both are checked because circle 32's newest post is newer than its last_activity_at.
        """
        stamps = [t for t in (self.last_activity_at, self.latest_post_at) if t is not None]
        if not stamps:
            return math.inf
        return max(0.0, (as_of - max(stamps)).total_seconds() / 86400)

    @property
    def engagement_per_post(self) -> float:
        return self.engagement_30d / self.posts_30d if self.posts_30d else 0.0

    @property
    def leader_share(self) -> float:
        """Share of the last 30 days' posts written by the leader."""
        return self.leader_posts_30d / self.posts_30d if self.posts_30d else 0.0


def _maybe_timestamp(value: str | None) -> datetime | None:
    return parse_timestamp(value) if value else None


@dataclass(frozen=True)
class Member:
    """The member asking for recommendations."""

    id: int
    first_name: str
    location: str | None
    bio: str | None
    topic_interests: tuple[str, ...]
    circle_ids: frozenset[int]

    @classmethod
    def from_user(cls, user: dict, circle_ids: set[int]) -> Member:
        return cls(
            id=user["id"],
            first_name=user["first_name"],
            location=user["location"],
            bio=user["bio"],
            topic_interests=tuple(user["topic_interests"]),
            circle_ids=frozenset(circle_ids),
        )

    @property
    def city(self) -> str | None:
        return city_of(self.location)


# ---------------------------------------------------------------------------
# Interest profile: stated interests, then the bio, then the member's Circles
# ---------------------------------------------------------------------------

STATED, BIO, CIRCLE = "stated", "bio", "circle"
SOURCE_WEIGHTS = {STATED: 1.0, BIO: 0.6, CIRCLE: 0.4}

PERSONALIZED, INFERRED, COLD_START = "personalized", "inferred", "cold_start"


@dataclass(frozen=True)
class Interest:
    topic: str
    source: str
    weight: float
    via_circle: str | None = None  # for CIRCLE interests: the Circle it came from


# Phrases that signal a topic in free text such as a bio. A trailing * matches any
# word ending, so "mentor*" matches mentor, mentoring and mentorship.
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "leadership-skills": ("leadership", "leader*", "leading"),
    "managing-a-team": ("first-time manager", "new manager", "people manager", "managing a team", "my team"),
    "giving-feedback": ("feedback", "performance review*"),
    "negotiation": ("negotiat*", "comp conversation*", "compensation", "salary", "pay equity"),
    "getting-promoted": ("promot*", "next level", "stretch project*"),
    "managing-up": ("managing up", "manage up", "my manager", "my boss"),
    "visibility-recognition": ("visibility", "recognition", "get noticed"),
    "networking": ("networking",),
    "sponsorship-mentorship": ("mentor*", "sponsor*"),
    "confidence": ("confidence", "confident"),
    "imposter-syndrome": ("imposter", "impostor"),
    "stress-burnout": ("burnout", "burned out", "burnt out", "stress*"),
    "resilience": ("resilien*", "setback*", "bounce back"),
    "communication": ("communicat*", "talked over"),
    "difficult-conversations": ("difficult conversation*", "hard conversation*", "tough conversation*"),
    "gender-bias": ("gender bias", "bias"),
    "allyship": ("ally", "allies", "allyship"),
    "working-motherhood": ("working mom*", "working mother*", "mom of", "mother of"),
    "public-speaking": ("public speaking", "presenting", "presentation*", "executive presence"),
    "career-breaks": ("career break*", "returning to work", "return to work", "return after leave"),
    "work-life-integration": ("work-life", "boundar*", "work life balance"),
    "being-the-only-one": ("only woman", "only one in the room"),
}


def _keyword_pattern(phrase: str) -> re.Pattern[str]:
    if phrase.endswith("*"):
        return re.compile(rf"\b{re.escape(phrase[:-1])}\w*", re.IGNORECASE)
    return re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)


_KEYWORD_PATTERNS = {
    topic: tuple(_keyword_pattern(p) for p in phrases) for topic, phrases in TOPIC_KEYWORDS.items()
}


def topics_in_text(text: str | None) -> list[str]:
    """Topics whose keywords appear in the text, in taxonomy order."""
    if not text:
        return []
    return [t for t, patterns in _KEYWORD_PATTERNS.items() if any(p.search(text) for p in patterns)]


def build_profile(member: Member, circles_by_id: dict[int, Circle]) -> dict[str, Interest]:
    """Everything the member has told us about their interests, strongest source first.

    Stated interests always count. Bio keywords add topics not already stated.
    The topics of the member's own Circles count only when there are no stated
    interests, as a hint at what else they'd value.
    """
    profile: dict[str, Interest] = {}
    for topic in member.topic_interests:
        profile.setdefault(topic, Interest(topic, STATED, SOURCE_WEIGHTS[STATED]))
    for topic in topics_in_text(member.bio):
        profile.setdefault(topic, Interest(topic, BIO, SOURCE_WEIGHTS[BIO]))
    if not member.topic_interests:
        for circle_id in sorted(member.circle_ids):
            circle = circles_by_id.get(circle_id)
            if circle is not None and circle.topic:
                profile.setdefault(
                    circle.topic,
                    Interest(circle.topic, CIRCLE, SOURCE_WEIGHTS[CIRCLE], via_circle=circle.name),
                )
    return profile


def strategy_for(member: Member, profile: dict[str, Interest]) -> str:
    """personalized: stated interests. inferred: bio or Circles only. cold_start: nothing."""
    if member.topic_interests:
        return PERSONALIZED
    return INFERRED if profile else COLD_START
