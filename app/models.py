"""Data access layer. All SQL lives here; callers get plain dicts, sets and lists."""
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from app.seed import DEFAULT_DB_PATH

DbPath = str | Path


def get_connection(db_path: DbPath = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection with dict-like rows and foreign keys enforced."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_user(user_id: int, db_path: DbPath = DEFAULT_DB_PATH) -> dict | None:
    """Return the user's fields plus topic_interests, or None if no such user."""
    with closing(get_connection(db_path)) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        interests = conn.execute(
            # rowid preserves the order the interests were listed in users.json
            "SELECT topic_slug FROM user_topics WHERE user_id = ? ORDER BY rowid",
            (user_id,),
        ).fetchall()

    user = dict(row)
    user["has_photo"] = bool(user["has_photo"])
    user["topic_interests"] = [r["topic_slug"] for r in interests]
    return user


def get_user_memberships(user_id: int, db_path: DbPath = DEFAULT_DB_PATH) -> set[int]:
    """Return the ids of every circle the user belongs to, in any role."""
    with closing(get_connection(db_path)) as conn:
        rows = conn.execute(
            "SELECT circle_id FROM memberships WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {r["circle_id"] for r in rows}


def get_topic_labels(db_path: DbPath = DEFAULT_DB_PATH) -> dict[str, str]:
    """Map each topic slug to its display label."""
    with closing(get_connection(db_path)) as conn:
        rows = conn.execute("SELECT slug, label FROM topics").fetchall()
    return {r["slug"]: r["label"] for r in rows}


_CANDIDATE_CIRCLES_SQL = """
SELECT
    c.*,
    t.label                              AS topic_label,
    leader.location                      AS leader_location,
    COALESCE(eng.total_reactions, 0)     AS total_reactions,
    COALESCE(eng.total_comments, 0)      AS total_comments,
    COALESCE(eng.total_saves, 0)         AS total_saves,
    COALESCE(eng.activity_post_count, 0) AS activity_post_count
FROM circles AS c
LEFT JOIN topics AS t ON t.slug = c.topic
LEFT JOIN (
    -- one leader per circle; MIN() keeps a single row if data ever has two
    SELECT m.circle_id, MIN(m.user_id) AS leader_id
    FROM memberships AS m
    WHERE m.role = 'leader'
    GROUP BY m.circle_id
) AS lm ON lm.circle_id = c.id
LEFT JOIN users AS leader ON leader.id = lm.leader_id
LEFT JOIN (
    -- aggregated separately so joining activity can't multiply circle rows
    SELECT
        circle_id,
        SUM(reaction_count) AS total_reactions,
        SUM(comment_count)  AS total_comments,
        SUM(save_count)     AS total_saves,
        COUNT(*)            AS activity_post_count
    FROM activity
    GROUP BY circle_id
) AS eng ON eng.circle_id = c.id
ORDER BY c.id
"""


def get_candidate_circles(db_path: DbPath = DEFAULT_DB_PATH) -> list[dict]:
    """Return every circle with its topic label, tags, leader location and engagement totals.

    No filtering happens here. Deciding which circles are eligible for a user
    is the recommender's job. Uses two queries total, regardless of circle count.
    """
    with closing(get_connection(db_path)) as conn:
        circle_rows = conn.execute(_CANDIDATE_CIRCLES_SQL).fetchall()
        tag_rows = conn.execute(
            # rowid preserves the order the tags were listed in circles.json
            "SELECT circle_id, tag_slug FROM circle_tags ORDER BY circle_id, rowid"
        ).fetchall()

    tags_by_circle: dict[int, list[str]] = defaultdict(list)
    for r in tag_rows:
        tags_by_circle[r["circle_id"]].append(r["tag_slug"])

    circles = []
    for row in circle_rows:
        circle = dict(row)
        circle["tags"] = tags_by_circle.get(circle["id"], [])
        circles.append(circle)
    return circles
