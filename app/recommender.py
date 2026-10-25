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


# ---------------------------------------------------------------------------
# Eligibility gates: Circles the member can't be offered
# ---------------------------------------------------------------------------

INACTIVE_AFTER_DAYS = 60


def exclusion_reasons(circle: Circle, member: Member, as_of: datetime) -> list[str]:
    """Every reason this Circle can't be recommended to this member. Empty means eligible."""
    reasons = []
    if circle.id in member.circle_ids:
        reasons.append("already_member")
    if circle.access != "public":
        reasons.append(circle.access)
    if circle.is_full:
        reasons.append("full")
    if circle.idle_days(as_of) >= INACTIVE_AFTER_DAYS:
        reasons.append("inactive")
    return reasons


# ---------------------------------------------------------------------------
# Scoring: relevance and activity, scaled by whether the member can attend
# ---------------------------------------------------------------------------

TAG_MATCH_FACTOR = 0.5  # a tag-only match counts half as much as a topic match
EXTRA_MATCH_BONUS = 0.1  # per additional interest the Circle also covers

RECENCY_DAYS = 14
POSTS_CAP, CHAT_CAP = 12, 100  # 30-day volume that earns full credit
ENGAGEMENT_CAP = 15  # reactions plus comments per post
POSTERS_CAP = 8  # distinct members posting in 30 days
LEADER_DOMINANCE = 0.8  # above this share of posts, the Circle is a broadcast

REACH_MULTIPLIERS = {
    "in_person_near": 1.15,
    "hybrid_near": 1.10,
    "virtual": 1.00,
    "hybrid": 1.00,
    "in_person_unknown": 0.80,
    "in_person_far": 0.40,
}

RELEVANCE_WEIGHT, ACTIVITY_WEIGHT = 0.6, 0.4
COLD_ACTIVITY_WEIGHT, COLD_OPEN_WEIGHT = 0.85, 0.15


@dataclass(frozen=True)
class Match:
    """How a Circle relates to the member's interests."""

    relevance: float
    interest: Interest | None  # the strongest matching interest
    via_tag: bool  # True when that interest matched a tag rather than the topic
    matched: tuple[Interest, ...]  # every matching interest, strongest first


NO_MATCH = Match(0.0, None, False, ())


def match(circle: Circle, profile: dict[str, Interest]) -> Match:
    hits = []
    for interest in profile.values():
        if circle.topic == interest.topic:
            hits.append((interest.weight, False, interest))
        elif interest.topic in circle.tags:
            hits.append((interest.weight * TAG_MATCH_FACTOR, True, interest))
    if not hits:
        return NO_MATCH
    hits.sort(key=lambda h: (-h[0], h[1], h[2].topic))
    best_value, via_tag, best = hits[0]
    relevance = min(1.0, best_value + EXTRA_MATCH_BONUS * (len(hits) - 1))
    return Match(relevance, best, via_tag, tuple(h[2] for h in hits))


def activity_score(circle: Circle, as_of: datetime) -> float:
    """A 0-1 measure of a living community: four equal parts.

    Recency, volume of posts and chat, engagement per post, and how many
    different members post. A Circle whose leader writes nearly everything
    gets half credit for participation.
    """
    recency = math.exp(-circle.idle_days(as_of) / RECENCY_DAYS)
    volume = 0.6 * min(circle.feed_posts_30d / POSTS_CAP, 1) + 0.4 * min(circle.chat_messages_30d / CHAT_CAP, 1)
    engagement = min(circle.engagement_per_post / ENGAGEMENT_CAP, 1)
    participation = min(circle.authors_30d / POSTERS_CAP, 1)
    if circle.leader_share > LEADER_DOMINANCE:
        participation *= 0.5
    return (recency + volume + engagement + participation) / 4


def reach(circle: Circle, member: Member) -> str:
    """How easily the member can attend, using the leader's city as the Circle's location."""
    near = member.city is not None and circle.leader_city == member.city
    if circle.format == "virtual":
        return "virtual"
    if circle.format == "hybrid":
        return "hybrid_near" if near else "hybrid"
    if near:
        return "in_person_near"
    if member.city is None or circle.leader_city is None:
        return "in_person_unknown"
    return "in_person_far"


def score(circle: Circle, member: Member, circle_match: Match, as_of: datetime, strategy: str) -> float:
    multiplier = REACH_MULTIPLIERS[reach(circle, member)]
    activity = activity_score(circle, as_of)
    if strategy == COLD_START:
        base = COLD_ACTIVITY_WEIGHT * activity + COLD_OPEN_WEIGHT * (circle.join_policy == "open")
    else:
        base = RELEVANCE_WEIGHT * circle_match.relevance + ACTIVITY_WEIGHT * activity
    return base * multiplier
