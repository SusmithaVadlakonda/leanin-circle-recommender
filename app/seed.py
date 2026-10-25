"""Load the seed JSON files in data/ into a fresh SQLite database.

Usage:
    python -m app.seed              # writes circles.db at the project root
    python -m app.seed path/to.db   # writes to a custom path
"""
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = PROJECT_ROOT / "circles.db"

TABLES = ["topics", "users", "user_topics", "circles", "circle_tags", "memberships", "activity"]


def _load(data_dir: Path, name: str) -> list[dict]:
    return json.loads((data_dir / f"{name}.json").read_text(encoding="utf-8"))


def normalize_slugs(values: list[str | None] | None) -> list[str]:
    """Trim, lowercase and deduplicate slugs, keeping their first-seen order.

    Tags are free-form, so " Negotiation " and "negotiation" are the same tag.
    """
    cleaned = (v.strip().lower() for v in (values or []) if v and v.strip())
    return list(dict.fromkeys(cleaned))


def _reset(db_path: Path) -> None:
    """Remove an existing database and any SQLite sidecar files."""
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)


def seed_db(db_path: str | Path = DEFAULT_DB_PATH, data_dir: str | Path = DATA_DIR) -> dict[str, int]:
    """Recreate the database at db_path from the JSON files in data_dir.

    Returns the row count of every table.
    """
    db_path = Path(db_path)
    data_dir = Path(data_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _reset(db_path)

    topics = _load(data_dir, "topics")
    users = _load(data_dir, "users")
    circles = _load(data_dir, "circles")
    memberships = _load(data_dir, "memberships")
    activity = _load(data_dir, "activity")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        with conn:  # one transaction: commits on success, rolls back on error
            conn.executemany(
                "INSERT INTO topics (id, slug, label, domain) VALUES (:id, :slug, :label, :domain)",
                topics,
            )

            conn.executemany(
                """INSERT INTO users (id, first_name, last_name, has_photo, bio, job_title, company,
                                      industry, location, joined_at, profile_completeness)
                   VALUES (:id, :first_name, :last_name, :has_photo, :bio, :job_title, :company,
                           :industry, :location, :joined_at, :profile_completeness)""",
                [{**u, "has_photo": int(bool(u["has_photo"]))} for u in users],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO user_topics (user_id, topic_slug) VALUES (?, ?)",
                [(u["id"], slug) for u in users for slug in normalize_slugs(u["topic_interests"])],
            )

            conn.executemany(
                """INSERT INTO circles (id, name, slug, description, topic, cover_image_url, format,
                                        access, join_policy, max_members, member_count, created_at,
                                        last_activity_at, feed_posts_30d, chat_messages_30d)
                   VALUES (:id, :name, :slug, :description, :topic, :cover_image_url, :format,
                           :access, :join_policy, :max_members, :member_count, :created_at,
                           :last_activity_at, :feed_posts_30d, :chat_messages_30d)""",
                circles,
            )
            conn.executemany(
                "INSERT OR IGNORE INTO circle_tags (circle_id, tag_slug) VALUES (?, ?)",
                [(c["id"], slug) for c in circles for slug in normalize_slugs(c["tags"])],
            )

            conn.executemany(
                """INSERT INTO memberships (user_id, circle_id, role, joined_at)
                   VALUES (:user_id, :circle_id, :role, :joined_at)""",
                memberships,
            )

            conn.executemany(
                """INSERT INTO activity (id, circle_id, author_user_id, body, reaction_count,
                                         comment_count, save_count, created_at)
                   VALUES (:id, :circle_id, :author_user_id, :body, :reaction_count,
                           :comment_count, :save_count, :created_at)""",
                activity,
            )

        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after seeding: {violations}")

        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally:
        conn.close()


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB_PATH
    counts = seed_db(db_path)
    print(f"Seeded {db_path}")
    width = max(len(t) for t in counts)
    for table, n in counts.items():
        print(f"  {table:<{width}}  {n:>4}")


if __name__ == "__main__":
    main()
