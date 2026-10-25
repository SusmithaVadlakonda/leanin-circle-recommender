"""Recommender units: gates and scoring.

Each test builds Circles that differ in one field, so it checks one rule at a time.
"""
from datetime import timedelta

import pytest
from factories import SNAPSHOT, make_circle, make_member

from app import models
from app.recommender import (
    Circle,
    Recommender,
    activity_score,
    build_profile,
    city_of,
    exclusion_reasons,
    match,
    score,
    strategy_for,
)
from app.service import load_member, load_recommender


def _score(circle, member, as_of=SNAPSHOT):
    profile = build_profile(member, {})
    return score(circle, member, match(circle, profile), as_of, strategy_for(member, profile))


def _idle(days, post_days=None, **overrides):
    return make_circle(
        last_activity_at=SNAPSHOT - timedelta(days=days),
        latest_post_at=None if post_days is None else SNAPSHOT - timedelta(days=post_days),
        **overrides,
    )


# ---- gates ------------------------------------------------------------------


def test_f1_full_when_member_count_reaches_capacity():
    member = make_member()
    assert "full" in exclusion_reasons(make_circle(member_count=12, max_members=12), member, SNAPSHOT)
    assert "full" in exclusion_reasons(make_circle(member_count=13, max_members=12), member, SNAPSHOT)
    assert "full" not in exclusion_reasons(make_circle(member_count=11, max_members=12), member, SNAPSHOT)
    assert "full" not in exclusion_reasons(make_circle(member_count=500, max_members=None), member, SNAPSHOT)


def test_f2_inactive_from_60_idle_days_using_the_newest_signal():
    member = make_member()
    assert "inactive" in exclusion_reasons(_idle(60), member, SNAPSHOT)
    assert "inactive" not in exclusion_reasons(_idle(59), member, SNAPSHOT)
    # A recent post keeps a Circle active even when last_activity_at is stale, and vice versa.
    assert "inactive" not in exclusion_reasons(_idle(235, post_days=20), member, SNAPSHOT)
    assert "inactive" not in exclusion_reasons(_idle(5, post_days=88), member, SNAPSHOT)
    assert "inactive" in exclusion_reasons(_idle(235, post_days=88), member, SNAPSHOT)


def test_f3_every_exclusion_reason_is_recorded(db_path):
    member = make_member(circle_ids={1})
    stale_unlisted = _idle(227, id=1, access="unlisted")
    assert exclusion_reasons(stale_unlisted, member, SNAPSHOT) == ["already_member", "unlisted", "inactive"]
    assert exclusion_reasons(make_circle(id=2), member, SNAPSHOT) == []

    circles = {row["id"]: Circle.from_row(row) for row in models.get_circle_catalog(SNAPSHOT, db_path)}
    assert exclusion_reasons(circles[21], make_member(), SNAPSHOT) == ["unlisted", "inactive"]
    assert exclusion_reasons(circles[20], make_member(), SNAPSHOT) == ["full"]


# ---- scoring ----------------------------------------------------------------


def test_r1_topic_match_beats_tag_match_beats_no_match():
    member = make_member(topic_interests=["negotiation"])
    on_topic = make_circle(id=1, topic="negotiation")
    by_tag = make_circle(id=2, topic="confidence", tags=("negotiation",))
    unrelated = make_circle(id=3, topic="confidence")
    assert _score(on_topic, member) > _score(by_tag, member) > _score(unrelated, member)


def test_r2_stated_beats_bio_beats_membership():
    circle = make_circle(id=1, topic="managing-a-team")
    stated = make_member(topic_interests=["managing-a-team"])
    from_bio = make_member(bio="First-time manager figuring it out alongside a great team.")
    from_circle = make_member(circle_ids={99})

    def via_circle_score(member):
        source = make_circle(id=99, topic="managing-a-team")
        profile = build_profile(member, {99: source})
        return score(circle, member, match(circle, profile), SNAPSHOT, strategy_for(member, profile))

    assert _score(circle, stated) > _score(circle, from_bio) > via_circle_score(from_circle)


def test_r3_activity_rises_with_each_signal_and_stays_between_0_and_1():
    base = make_circle()
    better = {
        "recency": make_circle(last_activity_at=SNAPSHOT, latest_post_at=SNAPSHOT),
        "posts": make_circle(feed_posts_30d=11),
        "chat": make_circle(chat_messages_30d=90),
        "engagement": make_circle(engagement_30d=110),
        "posting members": make_circle(authors_30d=7),
    }
    for signal, circle in better.items():
        assert activity_score(circle, SNAPSHOT) > activity_score(base, SNAPSHOT), signal

    huge = make_circle(feed_posts_30d=500, chat_messages_30d=9000, engagement_30d=9000, posts_30d=500, authors_30d=90)
    dead = _idle(400, feed_posts_30d=0, chat_messages_30d=0, engagement_30d=0, posts_30d=0, authors_30d=0)
    assert 0 <= activity_score(dead, SNAPSHOT) < activity_score(huge, SNAPSHOT) <= 1


def test_r4_a_leader_only_feed_scores_below_a_shared_one():
    shared = make_circle(posts_30d=8, authors_30d=5, leader_posts_30d=1)
    leader_heavy = make_circle(posts_30d=8, authors_30d=5, leader_posts_30d=7)
    broadcast = make_circle(posts_30d=8, authors_30d=1, leader_posts_30d=8)
    assert activity_score(shared, SNAPSHOT) > activity_score(leader_heavy, SNAPSHOT)
    assert activity_score(leader_heavy, SNAPSHOT) > activity_score(broadcast, SNAPSHOT)


def test_r5_location_scales_in_person_circles_without_hiding_them():
    member = make_member(topic_interests=["negotiation"], location="Seattle, WA")
    near = make_circle(format="in_person", leader_city="Seattle, WA")
    virtual = make_circle(format="virtual")
    unknown = make_circle(format="in_person", leader_city=None)
    far = make_circle(format="in_person", leader_city="Boston, MA")
    assert _score(near, member) > _score(virtual, member) > _score(unknown, member) > _score(far, member)
    assert exclusion_reasons(far, member, SNAPSHOT) == []

    hybrid_near = make_circle(format="hybrid", leader_city="Seattle, WA")
    hybrid_far = make_circle(format="hybrid", leader_city="Boston, MA")
    assert _score(hybrid_near, member) > _score(hybrid_far, member) == _score(virtual, member)


def test_r5_remote_is_not_a_city():
    assert city_of("Remote") is None and city_of(None) is None
    member = make_member(location="Remote")
    led_remotely = make_circle(format="in_person", leader_city=None)
    assert _score(led_remotely, member) == _score(make_circle(format="in_person", leader_city="Boston, MA"), make_member())


@pytest.mark.parametrize("capacity", [11, 20, None])
def test_r6_spots_left_do_not_change_the_score(capacity):
    member = make_member(topic_interests=["negotiation"])
    roomy = make_circle(member_count=10, max_members=None)
    assert _score(make_circle(member_count=10, max_members=capacity), member) == _score(roomy, member)


# ---- diversity and cold start ---------------------------------------------------


def _recommend(circles, member, limit=5):
    return Recommender(circles, {}, SNAPSHOT).recommend(member, limit=limit)


def _ids(result):
    return [r.circle.id for r in result.recommendations]


def test_r7_same_topic_circles_collapse_into_one_result():
    member = make_member(topic_interests=["negotiation", "confidence"])
    circles = [
        make_circle(id=10, topic="negotiation", feed_posts_30d=9),
        make_circle(id=11, topic="negotiation", feed_posts_30d=12),
        make_circle(id=12, topic="negotiation", feed_posts_30d=10),
        make_circle(id=13, topic="confidence"),
        make_circle(id=14, topic="networking"),
    ]
    # Three topic groups for three slots, so no backfill: grouping alone decides the list.
    result = _recommend(circles, member, limit=3)
    assert _ids(result) == [11, 13, 14]
    assert [c.id for c in result.recommendations[0].similar] == [12, 10]


def test_r7_backfills_when_there_are_fewer_topics_than_slots():
    member = make_member(topic_interests=["negotiation"])
    circles = [make_circle(id=i, topic="negotiation", feed_posts_30d=i) for i in (1, 2, 3)]
    result = _recommend(circles, member, limit=5)
    assert _ids(result) == [3, 2, 1]
    assert all(r.similar == () for r in result.recommendations)


def test_r7_circles_without_a_topic_never_group():
    result = _recommend([make_circle(id=1, topic=None), make_circle(id=2, topic=None)], make_member())
    assert sorted(_ids(result)) == [1, 2]


def test_r8_cold_start_prefers_open_circles_on_distinct_topics():
    member = make_member()
    circles = [
        make_circle(id=1, topic="negotiation", join_policy="request"),
        make_circle(id=2, topic="confidence", join_policy="open"),
        make_circle(id=3, topic="confidence", join_policy="open"),
        make_circle(id=4, topic="networking", join_policy="open"),
    ]
    result = _recommend(circles, member, limit=3)
    assert result.strategy == "cold_start"
    assert _ids(result) == [2, 4, 1]
    topics = [r.circle.topic for r in result.recommendations]
    assert len(set(topics)) == len(topics)


def test_r9_unmatched_interests_still_fill_the_list_and_ties_break_by_id():
    member = make_member(topic_interests=["allyship"])
    circles = [make_circle(id=i, topic=topic) for i, topic in ((5, "negotiation"), (3, "confidence"), (4, "networking"))]
    result = _recommend(circles, member)
    assert _ids(result) == [3, 4, 5]
    assert all(r.match.interest is None for r in result.recommendations)
    assert _ids(_recommend(circles, member)) == _ids(result)


def test_engine_on_the_seeded_data_excludes_and_explains_nothing_it_shouldnt(db_path):
    engine = load_recommender(db_path)
    result = engine.recommend(load_member(23, db_path))
    excluded = {e.circle.id: e.reasons for e in result.excluded}
    assert excluded[20] == ("full",) and excluded[21] == ("unlisted", "inactive")
    assert excluded[23] == ("already_member",)
    assert load_member(999, db_path) is None
