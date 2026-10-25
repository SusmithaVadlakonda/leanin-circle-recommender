"""Data layer: seeding."""
import json
import shutil
import sqlite3

from app.seed import DATA_DIR, normalize_slugs, seed_db

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


def test_d2_tags_are_trimmed_lowercased_and_deduplicated(db_path):
    assert normalize_slugs([" Negotiation ", "negotiation", "", None, "Confidence"]) == [
        "negotiation",
        "confidence",
    ]
    with sqlite3.connect(db_path) as conn:
        tags = [r[0] for r in conn.execute(
            "SELECT tag_slug FROM circle_tags WHERE circle_id = 17 ORDER BY rowid"
        )]
    # circles.json lists difficult-conversations twice for circle 17.
    assert tags == ["difficult-conversations", "managing-a-team"]


def test_d3_free_form_tag_seeds_without_error(tmp_path):
    data_dir = tmp_path / "data"
    shutil.copytree(DATA_DIR, data_dir)
    circles_file = data_dir / "circles.json"
    circles = json.loads(circles_file.read_text())
    circles[0]["tags"].append(" Women in Tech ")
    circles_file.write_text(json.dumps(circles))

    db = tmp_path / "free-form.db"
    seed_db(db, data_dir=data_dir)  # raises if any foreign key is violated

    with sqlite3.connect(db) as conn:
        tags = {r[0] for r in conn.execute("SELECT tag_slug FROM circle_tags WHERE circle_id = 1")}
        assert "women in tech" in tags
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_d4_user_lookups_use_the_primary_key_index(db_path):
    with sqlite3.connect(db_path) as conn:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT circle_id FROM memberships WHERE user_id = 7"
        ).fetchall()
        redundant = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_memberships_user_id'"
        ).fetchall()
    assert "sqlite_autoindex_memberships_1" in plan[0][3]
    assert redundant == []
