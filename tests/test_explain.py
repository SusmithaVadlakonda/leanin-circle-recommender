"""Explanations: reason selection, templates and copy rules."""
import json
import re
from datetime import timedelta

import pytest
from factories import SNAPSHOT, make_circle, make_member

from app.explain import MAX_EXPLANATION_CHARS, explain, nudge
from app.recommender import Recommender
from app.seed import DATA_DIR

LABELS = {
    "negotiation": "Negotiation",
    "confidence": "Confidence",
    "networking": "Networking",
    "managing-a-team": "Managing a team",
}
FORBIDDEN = re.compile(r"\b(score[sd]?|weights?|algorithm|ranking|ranked)\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def everyone(engine, members):
    """Every user's explained results on the seeded data."""
    return {uid: explain(engine.recommend(m), engine.topic_labels) for uid, m in members.items()}


def _explained(circles, member, labels=LABELS):
    result = Recommender(circles, labels, SNAPSHOT).recommend(member, limit=len(circles))
    return {item.recommendation.circle.id: item for item in explain(result, labels)}


def _slot(circles, member, circle_id, slot):
    return _explained(circles, member)[circle_id].reasons[slot]


def test_x1_three_reasons_within_the_length_limit(everyone):
    for uid, results in everyone.items():
        assert len(results) == 5, uid
        for item in results:
            assert len(item.reasons) == 3
            assert item.explanation == " ".join(r.text for r in item.reasons)
            assert len(item.explanation) <= MAX_EXPLANATION_CHARS, (uid, item.explanation)


def test_x2_each_fit_source_has_its_own_copy():
    def fit(circle, member, circles=()):
        reason = _slot([circle, *circles], member, circle.id, 0)
        return reason.code, reason.text

    assert fit(make_circle(id=1, topic="negotiation"), make_member(topic_interests=["negotiation"])) == (
        "interest_topic",
        "Focused on Negotiation, one of your interests.",
    )
    assert fit(
        make_circle(id=1, topic="negotiation", tags=("confidence",)),
        make_member(topic_interests=["negotiation", "confidence"]),
    ) == ("interest_multi", "Covers Negotiation and Confidence, both on your list.")
    assert fit(
        make_circle(id=1, topic="networking", tags=("confidence",)), make_member(topic_interests=["confidence"])
    ) == ("interest_tag", "Also covers Confidence, one of your interests.")
    assert fit(
        make_circle(id=1, topic="managing-a-team"),
        make_member(bio="First-time manager figuring it out alongside a great team."),
    ) == ("bio_match", "Fits what you wrote in your bio about Managing a team.")
    assert fit(
        make_circle(id=1, topic="networking"),
        make_member(circle_ids={99}),
        circles=[make_circle(id=99, name="Network & Grow", topic="networking")],
    ) == ("circle_match", "Similar focus to Network & Grow, a Circle you're in.")
    assert fit(make_circle(id=1, topic="networking"), make_member(topic_interests=["allyship"])) == (
        "explore",
        "A change of pace from your profile's topics, focused on Networking.",
    )
    assert fit(make_circle(id=1, topic=None), make_member(topic_interests=["allyship"])) == (
        "explore",
        "A change of pace from the topics in your profile.",
    )
    assert fit(make_circle(id=1), make_member()) == (
        "popular",
        "One of the most active Circles right now, focused on Negotiation.",
    )
    assert fit(make_circle(id=1, topic=None), make_member()) == (
        "popular",
        "One of the most active Circles right now.",
    )
    sleepy = make_circle(
        id=1,
        feed_posts_30d=1,
        chat_messages_30d=2,
        posts_30d=1,
        authors_30d=1,
        engagement_30d=2,
        last_activity_at=SNAPSHOT - timedelta(days=40),
        latest_post_at=SNAPSHOT - timedelta(days=40),
    )
    assert fit(sleepy, make_member()) == (
        "starter",
        "A good place to start exploring Circles, focused on Negotiation.",
    )


def test_x2_activity_copy_states_the_strongest_true_fact():
    member = make_member()

    def activity(**overrides):
        reason = _slot([make_circle(id=1, **overrides)], member, 1, 1)
        return reason.code, reason.text

    assert activity(authors_30d=9) == ("members_posting", "9 members posted in the last 30 days.")
    assert activity(authors_30d=4, feed_posts_30d=11) == ("busy", "11 posts in the last 30 days.")
    quiet = {"authors_30d": 2, "feed_posts_30d": 2, "latest_post_at": None}
    assert activity(**quiet, last_activity_at=SNAPSHOT - timedelta(days=3)) == ("active_week", "Active this week.")
    assert activity(**quiet, last_activity_at=SNAPSHOT - timedelta(days=20)) == (
        "active_month",
        "Active in the last month.",
    )
    assert activity(**quiet, last_activity_at=SNAPSHOT - timedelta(days=45)) == (
        "quiet",
        "Last active 45 days ago.",
    )


def test_x2_take_part_copy_follows_policy_then_location():
    member = make_member(location="Seattle, WA")

    def take_part(**overrides):
        return _slot([make_circle(id=1, **overrides)], member, 1, 2).text

    assert take_part(join_policy="request", format="in_person", leader_city="Seattle, WA") == (
        "Request to join; the leader approves new members."
    )
    assert take_part(format="in_person", leader_city="Seattle, WA") == "Led from Seattle, WA, close to you."
    assert take_part(format="hybrid", leader_city="Seattle, WA") == "Led from Seattle, WA, close to you."
    assert take_part(format="virtual") == "Meets virtually, so you can join from anywhere."
    assert take_part(format="hybrid", leader_city="Boston, MA") == "Hybrid, so you can join online."
    assert take_part(format="in_person", leader_city="Boston, MA") == "Meets in person, led from Boston, MA."
    assert take_part(format="in_person", leader_city=None) == "Meets in person."


def test_x3_labels_not_slugs_and_numbers_from_the_data(everyone):
    slugs = [t["slug"] for t in json.loads((DATA_DIR / "topics.json").read_text())]
    for results in everyone.values():
        for item in results:
            circle = item.recommendation.circle
            assert not any(slug in item.explanation for slug in slugs), item.explanation
            activity = item.reasons[1]
            if activity.code == "members_posting":
                assert activity.text.startswith(f"{circle.authors_30d} members")
            if activity.code == "busy":
                assert activity.text.startswith(f"{circle.feed_posts_30d} posts")


def test_x4_request_to_join_is_always_disclosed(everyone):
    for results in everyone.values():
        for item in results:
            if item.recommendation.circle.join_policy == "request":
                assert item.reasons[2].code == "request_to_join"
            assert "open to join" not in item.explanation.lower()


def test_x5_copy_never_mentions_internals_or_quotes_member_text(everyone, members):
    posts = {a["body"] for a in json.loads((DATA_DIR / "activity.json").read_text())}
    for uid, results in everyone.items():
        bio = members[uid].bio
        for item in results:
            assert not FORBIDDEN.search(item.explanation), item.explanation
            assert not any(post in item.explanation for post in posts)
            assert not (bio and bio in item.explanation)


def test_x6_a_different_explainer_changes_words_not_ranking(engine, members):
    class Shout:
        source = "fake"

        def render(self, fact):
            return fact.code.upper()

    result = engine.recommend(members[7])
    template = explain(result, engine.topic_labels)
    shouted = explain(result, engine.topic_labels, Shout())
    assert [i.recommendation.circle.id for i in shouted] == [i.recommendation.circle.id for i in template]
    assert shouted[0].explanation == "INTEREST_TOPIC MEMBERS_POSTING NEAR_YOU"
    assert template[0].explanation != shouted[0].explanation


def test_nudge_only_when_interests_are_missing():
    assert nudge("personalized") is None
    assert "interests" in nudge("inferred")
    assert "interests" in nudge("cold_start")
