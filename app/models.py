"""Data access layer. All SQL lives here; callers get plain dicts, sets and lists."""
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from app.seed import DEFAULT_DB_PATH
from app.timestamps import format_timestamp, parse_timestamp

DbPath = str | Path

ACTIVITY_WINDOW_DAYS = 30


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
    """Return the ids of every Circle the user belongs to, in any role."""
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


def get_snapshot_time(db_path: DbPath = DEFAULT_DB_PATH) -> datetime:
    """Return the latest timestamp in the data, which serves as "now" for a frozen snapshot."""
    with closing(get_connection(db_path)) as conn:
        latest = conn.execute(
            """SELECT MAX(ts) FROM (
                   SELECT MAX(last_activity_at) AS ts FROM circles
                   UNION ALL
                   SELECT MAX(created_at) FROM activity
               )"""
        ).fetchone()[0]
    if latest is None:
        raise ValueError("The database has no activity timestamps to anchor on.")
    return parse_timestamp(latest)


_CATALOG_SQL = """
WITH leader AS (
    -- One leader per Circle. MIN() keeps a single row if a Circle ever has two.
    SELECT circle_id, MIN(user_id) AS leader_id
    FROM memberships
    WHERE role = 'leader'
    GROUP BY circle_id
),
latest AS (
    SELECT circle_id, MAX(created_at) AS latest_post_at
    FROM activity
    WHERE created_at <= :as_of
    GROUP BY circle_id
),
recent AS (
    -- Posts in the window before the snapshot. Aggregated on its own so the
    -- join below can't multiply Circle rows.
    SELECT a.circle_id,
           COUNT(*)                                AS posts_30d,
           COUNT(DISTINCT a.author_user_id)        AS authors_30d,
           SUM(a.author_user_id = l.leader_id)     AS leader_posts_30d,
           SUM(a.reaction_count + a.comment_count) AS engagement_30d
    FROM activity AS a
    LEFT JOIN leader AS l ON l.circle_id = a.circle_id
    WHERE a.created_at > :since AND a.created_at <= :as_of
    GROUP BY a.circle_id
)
SELECT c.*,
       t.label                          AS topic_label,
       l.leader_id                      AS leader_id,
       u.location                       AS leader_location,
       lp.latest_post_at                AS latest_post_at,
       COALESCE(r.posts_30d, 0)         AS posts_30d,
       COALESCE(r.authors_30d, 0)       AS authors_30d,
       COALESCE(r.leader_posts_30d, 0)  AS leader_posts_30d,
       COALESCE(r.engagement_30d, 0)    AS engagement_30d
FROM circles AS c
LEFT JOIN topics AS t  ON t.slug = c.topic
LEFT JOIN leader AS l  ON l.circle_id = c.id
LEFT JOIN users  AS u  ON u.id = l.leader_id
LEFT JOIN latest AS lp ON lp.circle_id = c.id
LEFT JOIN recent AS r  ON r.circle_id = c.id
ORDER BY c.id
"""


def get_circle_catalog(as_of: datetime, db_path: DbPath = DEFAULT_DB_PATH) -> list[dict]:
    """Return every Circle with the features ranking needs, as of a point in time.

    Each dict holds the Circle's columns plus topic_label, tags, leader_id,
    leader_location, latest_post_at, and for the 30 days before as_of:
    posts_30d, authors_30d (distinct members posting), leader_posts_30d and
    engagement_30d (reactions plus comments).

    Nothing is filtered: deciding what a member can join is the recommender's
    job. Two queries in total, however many Circles there are.
    """
    params = {
        "as_of": format_timestamp(as_of),
        "since": format_timestamp(as_of - timedelta(days=ACTIVITY_WINDOW_DAYS)),
    }
    with closing(get_connection(db_path)) as conn:
        circle_rows = conn.execute(_CATALOG_SQL, params).fetchall()
        tag_rows = conn.execute(
            # rowid preserves the order the tags were listed in circles.json
            "SELECT circle_id, tag_slug FROM circle_tags ORDER BY circle_id, rowid"
        ).fetchall()

    tags_by_circle: dict[int, list[str]] = defaultdict(list)
    for r in tag_rows:
        tags_by_circle[r["circle_id"]].append(r["tag_slug"])

    catalog = []
    for row in circle_rows:
        circle = dict(row)
        circle["tags"] = tags_by_circle.get(circle["id"], [])
        catalog.append(circle)
    return catalog
