PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS topics (
    id      INTEGER PRIMARY KEY,
    slug    TEXT NOT NULL UNIQUE,
    label   TEXT NOT NULL,
    domain  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY,
    first_name           TEXT NOT NULL,
    last_name            TEXT NOT NULL,
    has_photo            INTEGER NOT NULL CHECK (has_photo IN (0, 1)),
    bio                  TEXT,
    job_title            TEXT,
    company              TEXT,
    industry             TEXT,
    location             TEXT,
    joined_at            TEXT NOT NULL,
    profile_completeness REAL NOT NULL CHECK (profile_completeness BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS circles (
    id                 INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    slug               TEXT NOT NULL UNIQUE,
    description        TEXT,
    topic              TEXT REFERENCES topics (slug),
    cover_image_url    TEXT,
    format             TEXT NOT NULL CHECK (format IN ('in_person', 'virtual', 'hybrid')),
    access             TEXT NOT NULL CHECK (access IN ('public', 'unlisted')),
    join_policy        TEXT NOT NULL CHECK (join_policy IN ('open', 'request')),
    max_members        INTEGER CHECK (max_members IS NULL OR max_members > 0),
    member_count       INTEGER NOT NULL DEFAULT 0 CHECK (member_count >= 0),
    created_at         TEXT NOT NULL,
    last_activity_at   TEXT,
    feed_posts_30d     INTEGER NOT NULL DEFAULT 0,
    chat_messages_30d  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memberships (
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    circle_id  INTEGER NOT NULL REFERENCES circles (id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('leader', 'member')),
    joined_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, circle_id)
);

CREATE TABLE IF NOT EXISTS activity (
    id              INTEGER PRIMARY KEY,
    circle_id       INTEGER NOT NULL REFERENCES circles (id) ON DELETE CASCADE,
    author_user_id  INTEGER NOT NULL REFERENCES users (id),
    body            TEXT NOT NULL,
    reaction_count  INTEGER NOT NULL DEFAULT 0,
    comment_count   INTEGER NOT NULL DEFAULT 0,
    save_count      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_topics (
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    topic_slug  TEXT NOT NULL REFERENCES topics (slug),
    PRIMARY KEY (user_id, topic_slug)
);

-- Tags are free-form per the dataset README, so tag_slug has no foreign key to topics.
-- Seeding trims, lowercases and deduplicates them.
CREATE TABLE IF NOT EXISTS circle_tags (
    circle_id  INTEGER NOT NULL REFERENCES circles (id) ON DELETE CASCADE,
    tag_slug   TEXT NOT NULL,
    PRIMARY KEY (circle_id, tag_slug)
);

-- Lookups by user_id on memberships, user_topics and circle_tags by circle_id are served by
-- each table's composite primary key, whose index is sorted by its first column.
-- The indexes below cover the lookups the primary keys can't.

-- Members of a Circle, including its leader.
CREATE INDEX IF NOT EXISTS idx_memberships_circle_id ON memberships (circle_id);
-- A Circle's posts in a time window: the 30-day activity features.
CREATE INDEX IF NOT EXISTS idx_activity_circle_time  ON activity (circle_id, created_at);
-- Circles on a topic, and Circles carrying a tag: candidate lookup by interest.
CREATE INDEX IF NOT EXISTS idx_circles_topic         ON circles (topic);
CREATE INDEX IF NOT EXISTS idx_circle_tags_tag_slug  ON circle_tags (tag_slug);
