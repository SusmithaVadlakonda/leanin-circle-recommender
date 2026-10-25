"""The four planted scenarios from the dataset README, plus a golden snapshot of their results.

Expectations come from the dataset README, not from the implementation.
"""
import json
from pathlib import Path

import pytest

from app.explain import nudge

pytestmark = pytest.mark.scenario

GOLDEN = Path(__file__).parent / "golden" / "planted.json"


def _ids(engine, members, user_id):
    return [r.circle.id for r in engine.recommend(members[user_id]).recommendations]


def test_s1_obvious_matches_come_first(engine, members):
    ids = _ids(engine, members, 7)
    assert ids[:2] == [5, 6]
    assert 4 not in ids  # user 7 already belongs to #4


def test_s2_near_duplicates_collapse_into_one_result(engine, members):
    result = engine.recommend(members[15])
    listed = [r for r in result.recommendations if r.circle.id in {10, 11, 12}]
    assert len(listed) == 1
    assert {c.id for c in listed[0].similar} == {10, 11, 12} - {listed[0].circle.id}


def test_s3_full_and_inactive_circles_never_rank(engine, members):
    ids = _ids(engine, members, 23)
    assert ids[0] == 22
    assert not {20, 21} & set(ids)


def test_s4_cold_start_offers_open_active_circles_on_five_topics(engine, members):
    result = engine.recommend(members[42])
    assert result.strategy == "cold_start"
    assert nudge(result.strategy)
    circles = [r.circle for r in result.recommendations]
    assert len(circles) == 5
    assert len({c.topic for c in circles}) == 5
    for circle in circles:
        assert circle.join_policy == "open" and circle.access == "public" and not circle.is_full
        assert circle.idle_days(engine.as_of) < 60
        assert circle.format in {"hybrid", "virtual"}  # user 42 has no location


def test_s5_planted_results_match_the_golden_snapshot(engine, members):
    golden = json.loads(GOLDEN.read_text())
    current = {str(user_id): _ids(engine, members, user_id) for user_id in (7, 15, 23, 42)}
    assert current == golden, "Ranking changed. If that's intended, run `make golden` and say why in the commit."
