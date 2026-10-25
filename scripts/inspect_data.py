"""Quick inspection of the seed JSON files in data/.

Usage: python3 scripts/inspect_data.py
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
ANCHOR = datetime(2026, 9, 21, tzinfo=timezone.utc)
INACTIVE_DAYS = 60
PLANTED_USERS = [7, 15, 23, 42]
FILES = ["topics", "users", "circles", "memberships", "activity"]


def load(name):
    return json.loads((DATA / f"{name}.json").read_text())


def ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def is_empty(v):
    return v is None or v == "" or v == []


def section(title):
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


d = {name: load(name) for name in FILES}
topics, users, circles = d["topics"], d["users"], d["circles"]
memberships, activity = d["memberships"], d["activity"]
topic_slugs = {t["slug"] for t in topics}
circle_by_id = {c["id"]: c for c in circles}
user_by_id = {u["id"]: u for u in users}

# ---- row counts and null/empty fields --------------------------------------
section("Row counts and null / empty fields")
for name in FILES:
    rows = d[name]
    keys = sorted({k for r in rows for k in r})
    ragged = [k for k in keys if sum(k in r for r in rows) != len(rows)]
    print(f"{name}: {len(rows)} rows, {len(keys)} fields"
          + (f"  (fields missing on some rows: {ragged})" if ragged else ""))
    for k in keys:
        nulls = sum(r.get(k) is None for r in rows)
        empties = sum(r.get(k) in ("", []) for r in rows)
        if nulls or empties:
            print(f"   {k:<22} null={nulls:<3} empty={empties}")

# ---- referential integrity --------------------------------------------------
section("Referential integrity")
dup_members = [k for k, n in Counter((m["user_id"], m["circle_id"]) for m in memberships).items() if n > 1]
checks = {
    "memberships -> unknown user": sum(m["user_id"] not in user_by_id for m in memberships),
    "memberships -> unknown circle": sum(m["circle_id"] not in circle_by_id for m in memberships),
    "duplicate (user, circle) memberships": len(dup_members),
    "activity -> unknown circle": sum(a["circle_id"] not in circle_by_id for a in activity),
    "activity -> unknown author": sum(a["author_user_id"] not in user_by_id for a in activity),
    "circles with unknown topic": sum(c["topic"] is not None and c["topic"] not in topic_slugs for c in circles),
    "user interests with unknown topic": sum(t not in topic_slugs for u in users for t in u["topic_interests"]),
}
for label, n in checks.items():
    print(f"{label:<40} {n}")

actual_count = Counter(m["circle_id"] for m in memberships)
mismatch = [(c["id"], c["member_count"], actual_count[c["id"]]) for c in circles
            if c["member_count"] != actual_count[c["id"]]]
print(f"{'member_count != membership rows':<40} {len(mismatch)} {mismatch or ''}")
leaders = Counter(m["circle_id"] for m in memberships if m["role"] == "leader")
print(f"{'circles without exactly 1 leader':<40} {[cid for cid in circle_by_id if leaders[cid] != 1]}")

# ---- circle health ----------------------------------------------------------
section("Circles per topic")
per_topic = defaultdict(list)
for c in circles:
    per_topic[c["topic"]].append(c["id"])
for topic, ids in sorted(per_topic.items(), key=lambda kv: (-len(kv[1]), str(kv[0]))):
    print(f"{str(topic):<26} {len(ids):>2}  {ids}")
unused = sorted(topic_slugs - set(per_topic))
print(f"topics with no circle: {unused}")

last_post = {}
for a in activity:
    t = ts(a["created_at"])
    last_post[a["circle_id"]] = max(t, last_post.get(a["circle_id"], t))


def days_since(t):
    return (ANCHOR - t).days if t else None


def flags(c):
    out = []
    if c["access"] != "public":
        out.append(c["access"])
    if c["max_members"] is not None and c["member_count"] >= c["max_members"]:
        out.append("FULL")
    if days_since(ts(c["last_activity_at"])) >= INACTIVE_DAYS:
        out.append("INACTIVE")
    if c["join_policy"] == "request":
        out.append("request-to-join")
    return out


def circle_line(c):
    la = days_since(ts(c["last_activity_at"]))
    lp = days_since(last_post.get(c["id"]))
    cap = c["max_members"] if c["max_members"] is not None else "-"
    return (f"#{c['id']:<3} {c['name']:<28} topic={str(c['topic']):<24} "
            f"members={c['member_count']}/{cap:<3} posts30={c['feed_posts_30d']:<3} "
            f"last_activity={la}d last_post={'none' if lp is None else f'{lp}d'} {' '.join(flags(c))}")


section("Unlisted circles")
for c in circles:
    if c["access"] == "unlisted":
        print(circle_line(c))

section("Full circles (member_count >= max_members)")
for c in circles:
    if c["max_members"] is not None and c["member_count"] >= c["max_members"]:
        print(circle_line(c))
print(f"uncapped circles (max_members null): {sum(c['max_members'] is None for c in circles)}")

section(f"Inactive circles (no activity in {INACTIVE_DAYS}+ days before {ANCHOR.date()})")
for c in circles:
    by_field = days_since(ts(c["last_activity_at"])) >= INACTIVE_DAYS
    lp = days_since(last_post.get(c["id"]))
    by_posts = lp is None or lp >= INACTIVE_DAYS
    if by_field or by_posts:
        print(circle_line(c) + f"  [by last_activity_at={by_field}, by activity.json={by_posts}]")
future = [a["id"] for a in activity if ts(a["created_at"]) > ANCHOR]
print(f"activity rows dated after the anchor: {len(future)}")

# ---- tags ---------------------------------------------------------------------
section("Tags")
dup_within = {c["id"]: [t for t, n in Counter(c["tags"]).items() if n > 1] for c in circles}
dup_within = {k: v for k, v in dup_within.items() if v}
print(f"circles with a tag repeated inside their own list: {dup_within or 'none'}")
tag_echo = [c["id"] for c in circles if c["topic"] and c["topic"] in c["tags"]]
print(f"circles whose tags repeat their primary topic: {len(tag_echo)} {tag_echo}")
missing_topic_tag = [c["id"] for c in circles if c["topic"] and c["topic"] not in c["tags"]]
print(f"circles whose tags omit their primary topic: {len(missing_topic_tag)} {missing_topic_tag}")
print(f"tags not in topics.json: {sorted({t for c in circles for t in c['tags']} - topic_slugs) or 'none'}")
print("tag frequency:", dict(Counter(t for c in circles for t in c["tags"]).most_common()))
dup_names = defaultdict(list)
for c in circles:
    dup_names[c["slug"]].append(c["id"])
print(f"duplicate slugs: {[v for v in dup_names.values() if len(v) > 1] or 'none'}")

# ---- planted users --------------------------------------------------------------
section("Planted test users")
joined = defaultdict(set)
for m in memberships:
    joined[m["user_id"]].add(m["circle_id"])

for uid in PLANTED_USERS:
    u = user_by_id[uid]
    print(f"\nUser {uid}: {u['first_name']} {u['last_name']} | {u['job_title']} @ {u['company']} | "
          f"{u['location']} | joined {u['joined_at'][:10]} | completeness={u['profile_completeness']}")
    print(f"  bio: {u['bio']}")
    print(f"  interests: {u['topic_interests'] or 'NONE (cold start)'}")
    for cid in sorted(joined[uid]):
        print(f"  member of  {circle_line(circle_by_id[cid])}")
    interests = set(u["topic_interests"])
    cands = [c for c in circles if c["id"] not in joined[uid]
             and (c["topic"] in interests or interests & set(c["tags"]))]
    if not cands:
        print("  candidates: none by topic/tag match; fallback = public, not full, active, by posts30:")
        fallback = [c for c in circles if c["id"] not in joined[uid] and not {"unlisted", "FULL", "INACTIVE"} & set(flags(c))]
        for c in sorted(fallback, key=lambda c: -c["feed_posts_30d"])[:5]:
            print(f"  fallback   {circle_line(c)}")
    for c in sorted(cands, key=lambda c: (c["topic"] not in interests, c["id"])):
        how = "topic" if c["topic"] in interests else "tag"
        print(f"  cand({how:<5}) {circle_line(c)}")
