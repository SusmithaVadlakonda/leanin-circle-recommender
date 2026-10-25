"""Data layer: seeding."""
from app.seed import seed_db

EXPECTED_COUNTS = {
    "topics": 22,
    "users": 100,
    "user_topics": 140,
    "circles": 40,
    "circle_tags": 82,
    "memberships": 441,
    "activity": 386,
}


def test_d1_seeding_twice_gives_identical_counts(tmp_path):
    path = tmp_path / "twice.db"
    first = seed_db(path)
    second = seed_db(path)
    assert first == second == EXPECTED_COUNTS
