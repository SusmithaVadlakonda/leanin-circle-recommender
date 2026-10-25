"""Member-facing explanations: reason codes chosen from the facts, then worded as copy.

Choosing the reasons is deterministic logic in this module. Wording them is an
Explainer's job, so a different explainer, such as one backed by an LLM, can
replace the templates without touching ranking or reason selection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.recommender import (
    BIO,
    COLD_START,
    INFERRED,
    PERSONALIZED,
    STATED,
    Circle,
    Recommendation,
    RecommendationSet,
    activity_score,
)

MAX_EXPLANATION_CHARS = 200

MEMBERS_POSTING_MIN = 5  # enough distinct posters to say so
BUSY_POSTS_MIN = 8
POPULAR_ACTIVITY_MIN = 0.7  # activity score needed to call a Circle one of the most active

TEMPLATES = {
    # Slot 1: why it fits
    "interest_topic": "Focused on {topic}, one of your interests.",
    "interest_multi": "Covers {topic} and {other_topic}, both on your list.",
    "interest_tag": "Also covers {topic}, one of your interests.",
    "bio_match": "Fits what you wrote in your bio about {topic}.",
    "circle_match": "Similar focus to {circle}, a Circle you're in.",
    "popular": "One of the most active Circles right now.",
    "starter": "A good place to start exploring Circles.",
    "explore": "A change of pace from the topics in your profile.",
    # Variants used when the Circle has a topic, so a list doesn't repeat one sentence.
    "popular_topic": "One of the most active Circles right now, focused on {topic}.",
    "starter_topic": "A good place to start exploring Circles, focused on {topic}.",
    "explore_topic": "A change of pace from your profile's topics, focused on {topic}.",
    # Slot 2: why it's active
    "members_posting": "{n} members posted in the last 30 days.",
    "busy": "{n} posts in the last 30 days.",
    "active_week": "Active this week.",
    "active_month": "Active in the last month.",
    "quiet": "Last active {n} days ago.",
    # Slot 3: how to take part
    "request_to_join": "Request to join; the leader approves new members.",
    "near_you": "Led from {city}, close to you.",
    "virtual": "Meets virtually, so you can join from anywhere.",
    "hybrid": "Hybrid, so you can join online.",
    "in_person_far": "Meets in person, led from {city}.",
    "in_person": "Meets in person.",
}

NUDGES = {
    PERSONALIZED: None,
    INFERRED: "Add a few interests to your profile for more personal picks.",
    COLD_START: "Add a few interests to your profile and we'll tailor these picks to you.",
}


@dataclass(frozen=True)
class ReasonFact:
    """A reason code and the only facts its copy may use."""

    code: str
    facts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Reason:
    code: str
    text: str


@dataclass(frozen=True)
class Explained:
    recommendation: Recommendation
    reasons: tuple[Reason, ...]
    explanation: str


class Explainer(Protocol):
    """Turns one reason into a sentence. `source` is reported in API responses."""

    source: str

    def render(self, fact: ReasonFact) -> str: ...


class TemplateExplainer:
    source = "template"

    def render(self, fact: ReasonFact) -> str:
        template = TEMPLATES.get(f"{fact.code}_topic") if "topic" in fact.facts else None
        return (template or TEMPLATES[fact.code]).format(**fact.facts)


def _label(slug: str, labels: dict[str, str]) -> str:
    return labels.get(slug, slug.replace("-", " ").capitalize())


def fit_reason(rec: Recommendation, strategy: str, labels: dict[str, str], as_of: datetime) -> ReasonFact:
    """Slot 1: why this Circle fits the member."""
    found = rec.match
    if found.interest is None:
        topic = {"topic": _label(rec.circle.topic, labels)} if rec.circle.topic else {}
        if strategy != COLD_START:
            return ReasonFact("explore", topic)
        is_popular = activity_score(rec.circle, as_of) >= POPULAR_ACTIVITY_MIN
        return ReasonFact("popular" if is_popular else "starter", topic)
    if found.interest.source == STATED:
        stated = [i for i in found.matched if i.source == STATED]
        if len(stated) >= 2:
            return ReasonFact(
                "interest_multi",
                {"topic": _label(stated[0].topic, labels), "other_topic": _label(stated[1].topic, labels)},
            )
        code = "interest_tag" if found.via_tag else "interest_topic"
        return ReasonFact(code, {"topic": _label(found.interest.topic, labels)})
    if found.interest.source == BIO:
        return ReasonFact("bio_match", {"topic": _label(found.interest.topic, labels)})
    return ReasonFact("circle_match", {"circle": found.interest.via_circle})


def activity_reason(circle: Circle, as_of: datetime) -> ReasonFact:
    """Slot 2: the strongest true statement about how active the Circle is."""
    if circle.authors_30d >= MEMBERS_POSTING_MIN:
        return ReasonFact("members_posting", {"n": circle.authors_30d})
    if circle.feed_posts_30d >= BUSY_POSTS_MIN:
        return ReasonFact("busy", {"n": circle.feed_posts_30d})
    idle = circle.idle_days(as_of)
    if idle <= 7:
        return ReasonFact("active_week")
    if idle <= 30:
        return ReasonFact("active_month")
    return ReasonFact("quiet", {"n": math.floor(idle)})


def take_part_reason(rec: Recommendation) -> ReasonFact:
    """Slot 3: what joining involves. A join request comes first because it sets expectations."""
    circle = rec.circle
    if circle.join_policy == "request":
        return ReasonFact("request_to_join")
    if rec.reach in ("in_person_near", "hybrid_near"):
        return ReasonFact("near_you", {"city": circle.leader_city})
    if rec.reach == "in_person_far":
        return ReasonFact("in_person_far", {"city": circle.leader_city})
    if rec.reach in ("virtual", "hybrid"):
        return ReasonFact(rec.reach)
    return ReasonFact("in_person")


def explain(
    result: RecommendationSet, labels: dict[str, str], explainer: Explainer | None = None
) -> list[Explained]:
    """Three reasons per result, one per slot, and the sentence they make together."""
    explainer = explainer or TemplateExplainer()
    explained = []
    for rec in result.recommendations:
        facts = (
            fit_reason(rec, result.strategy, labels, result.as_of),
            activity_reason(rec.circle, result.as_of),
            take_part_reason(rec),
        )
        reasons = tuple(Reason(f.code, explainer.render(f)) for f in facts)
        explained.append(Explained(rec, reasons, " ".join(r.text for r in reasons)))
    return explained


def nudge(strategy: str) -> str | None:
    """One profile prompt per response, or None when the member has stated interests."""
    return NUDGES[strategy]
