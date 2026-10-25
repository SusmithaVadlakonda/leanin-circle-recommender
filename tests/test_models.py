"""Data layer: lookups and the Circle catalog.

Expected values are computed straight from the JSON files, never from the code under test.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.seed import DATA_DIR

SNAPSHOT = datetime(2026, 9, 21, tzinfo=timezone.utc)


def _load(name):
    return json.loads((DATA_DIR / f"{name}.json").read_text())


def _ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_snapshot_time_is_the_latest_timestamp_in_the_data(db_path):
    assert models.get_snapshot_time(db_path) == SNAPSHOT


def test_d5_unknown_user_and_empty_cold_start_user(db_path):
    assert models.get_user(999, db_path) is None

    zoe = models.get_user(42, db_path)
    assert zoe["topic_interests"] == []
    assert zoe["has_photo"] is False
    assert models.get_user_memberships(42, db_path) == set()

    priya = models.get_user(7, db_path)
    assert priya["topic_interests"] == ["leadership-skills", "public-speaking"]
    assert models.get_user_memberships(7, db_path) == {4}


@pytest.fixture(scope="module")
def expected_features():
    """Per-Circle features computed directly from activity, memberships and users JSON."""
    users = {u["id"]: u for u in _load("users")}
    leaders = {m["circle_id"]: m["user_id"] for m in _load("memberships") if m["role"] == "leader"}
    activity = _load("activity")
    since = SNAPSHOT - timedelta(days=30)

    expected = {}
    for circle in _load("circles"):
        cid = circle["id"]
        posts = [a for a in activity if a["circle_id"] == cid]
        recent = [a for a in posts if since < _ts(a["created_at"]) <= SNAPSHOT]
        expected[cid] = {
            "leader_id": leaders[cid],
            "leader_location": users[leaders[cid]]["location"],
            "latest_post_at": max((a["created_at"] for a in posts), default=None),
            "posts_30d": len(recent),
            "authors_30d": len({a["author_user_id"] for a in recent}),
            "leader_posts_30d": sum(a["author_user_id"] == leaders[cid] for a in recent),
            "engagement_30d": sum(a["reaction_count"] + a["comment_count"] for a in recent),
        }
    return expected


def test_d6_catalog_features_match_the_raw_data(db_path, expected_features):
    catalog = models.get_circle_catalog(SNAPSHOT, db_path)
    assert [c["id"] for c in catalog] == sorted(expected_features)

    for circle in catalog:
        want = expected_features[circle["id"]]
        got = {key: circle[key] for key in want}
        assert got == want, f"circle {circle['id']}"
        # The README's feed_posts_30d agrees with the posts counted from activity.json.
        assert circle["posts_30d"] == circle["feed_posts_30d"]


def test_catalog_carries_labels_and_deduplicated_tags(db_path):
    by_id = {c["id"]: c for c in models.get_circle_catalog(SNAPSHOT, db_path)}
    assert by_id[22]["topic_label"] == "Getting promoted"
    assert by_id[27]["topic"] is None and by_id[27]["topic_label"] is None
    assert by_id[17]["tags"] == ["difficult-conversations", "managing-a-team"]
