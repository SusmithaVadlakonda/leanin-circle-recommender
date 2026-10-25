"""Rules every user's results must follow, checked for all 100 users in the dataset."""
import time

import pytest

from app.explain import MAX_EXPLANATION_CHARS, explain
from app.recommender import INACTIVE_AFTER_DAYS, exclusion_reasons

USERS = range(1, 101)


@pytest.fixture(scope="module")
def results(engine, members):
    return {user_id: engine.recommend(members[user_id]) for user_id in USERS}


@pytest.mark.parametrize("user_id", USERS)
def test_i1_never_a_circle_the_member_cannot_join(results, members, engine, user_id):
    member = members[user_id]
    # Similar Circles are offered to the member too, so they must pass the same gates.
    offered = [c for rec in results[user_id].recommendations for c in (rec.circle, *rec.similar)]
    for circle in offered:
        assert circle.id not in member.circle_ids
        assert circle.access == "public"
        assert not circle.is_full
        assert circle.idle_days(engine.as_of) < INACTIVE_AFTER_DAYS
        assert exclusion_reasons(circle, member, engine.as_of) == []


@pytest.mark.parametrize("user_id", USERS)
def test_i2_unique_results_with_scores_that_never_rise(results, user_id):
    recs = results[user_id].recommendations
    ids = [r.circle.id for r in recs]
    assert len(ids) == len(set(ids)) == 5
    scores = [r.score for r in recs]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("user_id", USERS)
def test_i3_no_two_results_share_a_topic(results, user_id):
    topics = [r.circle.topic for r in results[user_id].recommendations if r.circle.topic]
    assert len(topics) == len(set(topics))


@pytest.mark.parametrize("user_id", USERS)
def test_i4_every_explanation_follows_the_copy_rules(results, engine, user_id):
    for item in explain(results[user_id], engine.topic_labels):
        assert len(item.reasons) == 3
        assert 0 < len(item.explanation) <= MAX_EXPLANATION_CHARS


@pytest.mark.parametrize("user_id", USERS)
def test_i5_an_interest_signal_puts_a_matching_circle_first(results, user_id):
    result = results[user_id]
    if result.strategy != "cold_start":
        assert result.recommendations[0].match.interest is not None


def test_b1_ranking_every_user_takes_under_a_second(engine, members):
    start = time.perf_counter()
    for user_id in USERS:
        engine.recommend(members[user_id])
    assert time.perf_counter() - start < 1.0
